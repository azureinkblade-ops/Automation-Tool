// Separate protected-store bootstrap only. No grant transition or Docker capability.
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

internal sealed class Ea4eProtectedNetworkGrantStoreBootstrap : IDisposable
{
    internal const string Schema = "hermes.docker-network-grant-store/protected-v1";
    private const string MetadataDdl = "CREATE TABLE protected_grant_metadata (" +
        "schema_id TEXT NOT NULL,store_id TEXT NOT NULL," +
        "epoch TEXT NOT NULL,generation TEXT NOT NULL," +
        "state_hash TEXT NOT NULL)";
    private const string EventsDdl = "CREATE TABLE protected_grant_events (" +
        "generation INTEGER PRIMARY KEY,event_hash TEXT NOT NULL," +
        "prior_hash TEXT NOT NULL,state_hash TEXT NOT NULL)";
    private const string RowsDdl = "CREATE TABLE protected_grant_rows (" +
        "grant_id TEXT PRIMARY KEY,nonce TEXT NOT NULL UNIQUE," +
        "attempt_id TEXT NOT NULL UNIQUE,artifact_hash TEXT NOT NULL," +
        "state TEXT NOT NULL,one_attempt_budget TEXT NOT NULL)";
    private static readonly Regex Hex = new Regex(@"\A[0-9a-f]{64}\z");
    private readonly Ea4eProtectedSqlite db;

    private Ea4eProtectedNetworkGrantStoreBootstrap(Ea4eProtectedSqlite db)
    {
        this.db = db;
    }

    private static string InitialHash(string storeId, int epoch)
    {
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(Encoding.ASCII.GetBytes(
                Schema + "\n" + storeId + "\n" + epoch.ToString(
                    System.Globalization.CultureInfo.InvariantCulture))))
                .Replace("-", "").ToLowerInvariant();
    }

    private static void CheckPaths(string path, string anchor)
    {
        if (String.IsNullOrWhiteSpace(path) || String.IsNullOrWhiteSpace(anchor)
            || !Path.IsPathRooted(path) || !Path.IsPathRooted(anchor)
            || String.Equals(Path.GetFullPath(path), Path.GetFullPath(anchor),
                             StringComparison.OrdinalIgnoreCase)
            || !Directory.Exists(Path.GetDirectoryName(path))
            || !Directory.Exists(Path.GetDirectoryName(anchor)))
            throw new InvalidOperationException("Protected store paths denied");
    }

    private static string AnchorContent(string storeId, int epoch)
    {
        return Schema + "\n" + storeId + "\n" + epoch.ToString(
            System.Globalization.CultureInfo.InvariantCulture) + "\n0\n" +
            InitialHash(storeId, epoch) + "\n";
    }

    private static void VerifySchema(Ea4eProtectedSqlite db)
    {
        var expected = new Dictionary<string, string>(StringComparer.Ordinal) {
            { "protected_grant_metadata", MetadataDdl },
            { "protected_grant_events", EventsDdl },
            { "protected_grant_rows", RowsDdl },
        };
        using (var read = db.Prepare(
            "SELECT type,name,sql FROM sqlite_master WHERE type IN " +
            "('table','trigger','view') OR (type='index' AND sql IS NOT NULL)"))
        {
            while (read.Step())
            {
                string name = read.Text(1), ddl;
                if (read.Text(0) != "table" || name == null
                    || !expected.TryGetValue(name, out ddl) || read.Text(2) != ddl)
                    throw new InvalidOperationException("Protected store schema drift denied");
                expected.Remove(name);
            }
        }
        if (expected.Count != 0)
            throw new InvalidOperationException("Protected store schema incomplete");
    }

    internal static Ea4eProtectedNetworkGrantStoreBootstrap Initialize(
        string path, string anchor, string storeId, int epoch)
    {
        CheckPaths(path, anchor);
        if (storeId == null || !Hex.IsMatch(storeId) || epoch < 1
            || File.Exists(path) || File.Exists(anchor))
            throw new InvalidOperationException("Protected store initialization denied");
        var db = new Ea4eProtectedSqlite(path);
        try
        {
            db.Execute("BEGIN IMMEDIATE");
            db.Execute(MetadataDdl);
            db.Execute(EventsDdl);
            db.Execute(RowsDdl);
            using (var insert = db.Prepare(
                "INSERT INTO protected_grant_metadata VALUES (?,?,?,?,?)"))
            {
                insert.BindText(1, Schema);
                insert.BindText(2, storeId);
                insert.BindText(3, epoch.ToString(System.Globalization.CultureInfo.InvariantCulture));
                insert.BindText(4, "0");
                insert.BindText(5, InitialHash(storeId, epoch));
                if (insert.Step())
                    throw new InvalidOperationException("Protected metadata insert denied");
            }
            db.Execute("COMMIT");
            using (var stream = new FileStream(anchor, FileMode.CreateNew,
                                               FileAccess.Write, FileShare.None))
            {
                byte[] bytes = Encoding.ASCII.GetBytes(AnchorContent(storeId, epoch));
                stream.Write(bytes, 0, bytes.Length);
                stream.Flush(true);
            }
            return new Ea4eProtectedNetworkGrantStoreBootstrap(db);
        }
        catch
        {
            db.Dispose();
            throw;
        }
    }

    internal static Ea4eProtectedNetworkGrantStoreBootstrap Open(
        string path, string anchor)
    {
        CheckPaths(path, anchor);
        if (!File.Exists(path) || !File.Exists(anchor))
            throw new InvalidOperationException("Protected store missing");
        var db = new Ea4eProtectedSqlite(path);
        try
        {
            VerifySchema(db);
            string storeId, epochText, generation, stateHash;
            using (var read = db.Prepare(
                "SELECT schema_id,store_id,epoch,generation,state_hash " +
                "FROM protected_grant_metadata"))
            {
                if (!read.Step() || read.Text(0) != Schema)
                    throw new InvalidOperationException("Protected schema denied");
                storeId = read.Text(1);
                epochText = read.Text(2);
                generation = read.Text(3);
                stateHash = read.Text(4);
                if (read.Step())
                    throw new InvalidOperationException("Protected metadata count denied");
            }
            int epoch;
            if (storeId == null || !Hex.IsMatch(storeId)
                || !Int32.TryParse(epochText, System.Globalization.NumberStyles.None,
                    System.Globalization.CultureInfo.InvariantCulture, out epoch)
                || epoch < 1 || generation != "0"
                || stateHash != InitialHash(storeId, epoch))
                throw new InvalidOperationException("Protected metadata denied");
            foreach (string table in new[] { "protected_grant_events", "protected_grant_rows" })
                using (var read = db.Prepare("SELECT 1 FROM " + table + " LIMIT 1"))
                    if (read.Step())
                        throw new InvalidOperationException("Unqualified transition denied");
            byte[] anchorBytes = File.ReadAllBytes(anchor);
            byte[] expected = Encoding.ASCII.GetBytes(AnchorContent(storeId, epoch));
            if (anchorBytes.Length != expected.Length)
                throw new InvalidOperationException("Protected anchor denied");
            for (int index = 0; index < expected.Length; index++)
                if (anchorBytes[index] != expected[index])
                    throw new InvalidOperationException("Protected anchor denied");
            return new Ea4eProtectedNetworkGrantStoreBootstrap(db);
        }
        catch
        {
            db.Dispose();
            throw;
        }
    }

    // The caller must source these expectations outside the store and anchor.
    internal static Ea4eProtectedNetworkGrantStoreBootstrap OpenExpected(
        string path, string anchor, string expectedStoreId, int expectedEpoch)
    {
        if (expectedStoreId == null || !Hex.IsMatch(expectedStoreId)
            || expectedEpoch < 1)
            throw new InvalidOperationException("Expected protected store identity denied");
        var store = Open(path, anchor);
        try
        {
            using (var read = store.db.Prepare(
                "SELECT store_id,epoch FROM protected_grant_metadata"))
            {
                if (!read.Step() || read.Text(0) != expectedStoreId
                    || read.Text(1) != expectedEpoch.ToString(
                        System.Globalization.CultureInfo.InvariantCulture)
                    || read.Step())
                    throw new InvalidOperationException("Protected store substitution denied");
            }
            return store;
        }
        catch
        {
            store.Dispose();
            throw;
        }
    }

    public void Dispose()
    {
        db.Dispose();
    }
}

// Fake-only transactional qualification store. No protected issuer or Docker capability.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

internal sealed class Ea4eNetworkGrantV4Store : IDisposable
{
    private const string Schema = "hermes.docker-network-grant-store/v4";
    private const string MetadataDdl = "CREATE TABLE network_grant_v4_metadata (" +
        "schema_id TEXT NOT NULL,store_id TEXT NOT NULL,epoch TEXT NOT NULL," +
        "generation TEXT NOT NULL,state_hash TEXT NOT NULL,table_hash TEXT NOT NULL)";
    private const string JournalDdl = "CREATE TABLE network_grant_v4_journal (" +
        "generation INTEGER PRIMARY KEY,operation_hash TEXT NOT NULL," +
        "table_hash TEXT NOT NULL,event_hash TEXT NOT NULL," +
        "prior_hash TEXT NOT NULL,state_hash TEXT NOT NULL)";
    private const string RowsDdl = "CREATE TABLE network_grant_v4_rows (" +
        "grant_id TEXT PRIMARY KEY,artifact_json TEXT NOT NULL,state TEXT NOT NULL)";
    private static readonly Regex Hex = new Regex(@"\A[0-9a-f]{64}\z");
    private readonly Ea4eProtectedSqlite db;
    private readonly string anchorPrefix;
    private readonly string storeId;
    private readonly int epoch;
    private int generation;
    private string stateHash;

    private sealed class Head
    {
        internal string StoreId;
        internal int Epoch;
        internal int Generation;
        internal string StateHash;
        internal string TableHash;
    }

    private Ea4eNetworkGrantV4Store(Ea4eProtectedSqlite db, string prefix, Head head)
    {
        this.db = db;
        anchorPrefix = prefix;
        storeId = head.StoreId;
        epoch = head.Epoch;
        generation = head.Generation;
        stateHash = head.StateHash;
    }

    private static string Hash(string value)
    {
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(Encoding.ASCII.GetBytes(value)))
                .Replace("-", "").ToLowerInvariant();
    }

    private static void CheckPaths(string path, string prefix)
    {
        if (String.IsNullOrWhiteSpace(path) || String.IsNullOrWhiteSpace(prefix)
            || !Path.IsPathRooted(path) || !Path.IsPathRooted(prefix)
            || String.Equals(Path.GetFullPath(path), Path.GetFullPath(prefix),
                             StringComparison.OrdinalIgnoreCase)
            || !Directory.Exists(Path.GetDirectoryName(path))
            || !Directory.Exists(Path.GetDirectoryName(prefix)))
            throw new InvalidOperationException("Store paths denied");
    }

    private static string AnchorPath(string prefix, int generation)
    {
        return prefix + ".g" + generation.ToString("D8", CultureInfo.InvariantCulture);
    }

    private static Head ReadHead(Ea4eProtectedSqlite db)
    {
        using (var read = db.Prepare(
            "SELECT schema_id,store_id,epoch,generation,state_hash,table_hash " +
            "FROM network_grant_v4_metadata"))
        {
            if (!read.Step() || read.Text(0) != Schema)
                throw new InvalidOperationException("Store schema denied");
            var head = new Head {
                StoreId = read.Text(1),
                Epoch = Int32.Parse(read.Text(2), CultureInfo.InvariantCulture),
                Generation = Int32.Parse(read.Text(3), CultureInfo.InvariantCulture),
                StateHash = read.Text(4), TableHash = read.Text(5),
            };
            if (read.Step() || head.StoreId == null || !Hex.IsMatch(head.StoreId)
                || head.StateHash == null || !Hex.IsMatch(head.StateHash)
                || head.TableHash == null || !Hex.IsMatch(head.TableHash)
                || head.Epoch < 1 || head.Generation < 0 || head.Generation > 99999999)
                throw new InvalidOperationException("Store head denied");
            return head;
        }
    }

    private static void VerifySchema(Ea4eProtectedSqlite db)
    {
        var expected = new Dictionary<string, string>(StringComparer.Ordinal) {
            { "network_grant_v4_metadata", MetadataDdl },
            { "network_grant_v4_journal", JournalDdl },
            { "network_grant_v4_rows", RowsDdl },
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
                    throw new InvalidOperationException("Store schema drift denied");
                expected.Remove(name);
            }
        }
        if (expected.Count != 0)
            throw new InvalidOperationException("Store schema incomplete");
    }

    private static List<Ea4eNetworkGrantV4Digest.Row> ReadRows(
        Ea4eProtectedSqlite db, Head head)
    {
        var rows = new List<Ea4eNetworkGrantV4Digest.Row>();
        var nonces = new HashSet<string>(StringComparer.Ordinal);
        var attempts = new HashSet<string>(StringComparer.Ordinal);
        var targets = new HashSet<string>(StringComparer.Ordinal);
        using (var read = db.Prepare(
            "SELECT grant_id,artifact_json,state FROM network_grant_v4_rows ORDER BY grant_id"))
        {
            while (read.Step())
            {
                string id = read.Text(0), artifact = read.Text(1), state = read.Text(2);
                if (artifact == null || artifact.Length < 1 || artifact.Length > 16384)
                    throw new InvalidOperationException("Grant bytes denied");
                foreach (char item in artifact)
                    if (item < 0x20 || item > 0x7e)
                        throw new InvalidOperationException("Grant ASCII denied");
                byte[] bytes = Encoding.ASCII.GetBytes(artifact);
                var row = new Ea4eNetworkGrantV4Digest.Row(id, bytes, state);
                var identity = Ea4eNetworkMutationGrantCandidate.ReadCompleteIdentity(bytes);
                if (identity.GrantId != id || identity.StoreId != head.StoreId
                    || identity.StoreEpoch != head.Epoch
                    || !nonces.Add(identity.Nonce)
                    || !attempts.Add(identity.AttemptId + "|" + identity.Action)
                    || !targets.Add(identity.NetworkName))
                    throw new InvalidOperationException("Grant identity conflict denied");
                rows.Add(row);
            }
        }
        return rows;
    }

    private static string TableHash(Ea4eProtectedSqlite db, Head head)
    {
        return Ea4eNetworkGrantV4Digest.TableHash(ReadRows(db, head));
    }

    private static void WriteAnchor(string prefix, Head head)
    {
        using (var stream = new FileStream(AnchorPath(prefix, head.Generation),
            FileMode.CreateNew, FileAccess.Write, FileShare.None))
        using (var writer = new BinaryWriter(stream, Encoding.UTF8))
        {
            writer.Write(Schema);
            writer.Write(head.StoreId);
            writer.Write(head.Epoch);
            writer.Write(head.Generation);
            writer.Write(head.StateHash);
            writer.Write(head.TableHash);
            writer.Flush();
            stream.Flush(true);
        }
    }

    private static Head ReadAnchor(string path)
    {
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                                           FileShare.Read))
        using (var reader = new BinaryReader(stream, Encoding.UTF8))
        {
            if (stream.Length < 32 || stream.Length > 512 || reader.ReadString() != Schema)
                throw new InvalidOperationException("Anchor schema denied");
            var head = new Head {
                StoreId = reader.ReadString(), Epoch = reader.ReadInt32(),
                Generation = reader.ReadInt32(), StateHash = reader.ReadString(),
                TableHash = reader.ReadString(),
            };
            if (stream.Position != stream.Length)
                throw new InvalidOperationException("Anchor trailing bytes denied");
            return head;
        }
    }

    private static void Verify(Ea4eProtectedSqlite db, string prefix, Head head)
    {
        VerifySchema(db);
        string previous = Hash(Schema + head.StoreId +
            head.Epoch.ToString(CultureInfo.InvariantCulture));
        var states = new List<string> { previous };
        var tables = new List<string> {
            Ea4eNetworkGrantV4Digest.TableHash(
                new Ea4eNetworkGrantV4Digest.Row[0]),
        };
        int count = 0;
        using (var read = db.Prepare(
            "SELECT generation,operation_hash,table_hash,event_hash,prior_hash," +
            "state_hash FROM network_grant_v4_journal ORDER BY generation"))
        {
            while (read.Step())
            {
                count++;
                string operation = read.Text(1), table = read.Text(2);
                string eventHash = read.Text(3), next = read.Text(5);
                if (read.Text(0) != count.ToString(CultureInfo.InvariantCulture)
                    || operation == null || !Hex.IsMatch(operation)
                    || table == null || !Hex.IsMatch(table)
                    || eventHash != Hash(operation + table)
                    || read.Text(4) != previous || next == null
                    || next != Hash(previous + eventHash +
                        count.ToString("D20", CultureInfo.InvariantCulture)))
                    throw new InvalidOperationException("Store journal denied");
                previous = next;
                states.Add(next);
                tables.Add(table);
            }
        }
        if (count != head.Generation || previous != head.StateHash
            || tables[count] != head.TableHash || TableHash(db, head) != head.TableHash)
            throw new InvalidOperationException("Store rows drift denied");
        string directory = Path.GetDirectoryName(prefix);
        string stem = Path.GetFileName(prefix) + ".g";
        int anchorCount = 0;
        foreach (string file in Directory.GetFiles(directory, stem + "*"))
        {
            string suffix = Path.GetFileName(file).Substring(stem.Length);
            int candidate;
            if (suffix.Length != 8 || !Int32.TryParse(suffix,
                NumberStyles.None, CultureInfo.InvariantCulture, out candidate)
                || candidate > head.Generation)
                throw new InvalidOperationException("Unexpected anchor denied");
            anchorCount++;
        }
        if (anchorCount != head.Generation + 1)
            throw new InvalidOperationException("Anchor generation denied");
        for (int index = 0; index <= head.Generation; index++)
        {
            Head anchor = ReadAnchor(AnchorPath(prefix, index));
            if (anchor.StoreId != head.StoreId || anchor.Epoch != head.Epoch
                || anchor.Generation != index || anchor.StateHash != states[index]
                || anchor.TableHash != tables[index])
                throw new InvalidOperationException("Anchor mismatch denied");
        }
    }

    internal static Ea4eNetworkGrantV4Store Initialize(
        string path, string anchorPrefix, string storeId, int epoch)
    {
        CheckPaths(path, anchorPrefix);
        if (storeId == null || !Hex.IsMatch(storeId) || epoch < 1
            || File.Exists(path) || Directory.GetFiles(
                Path.GetDirectoryName(anchorPrefix),
                Path.GetFileName(anchorPrefix) + ".g*").Length != 0)
            throw new InvalidOperationException("Store initialization denied");
        var db = new Ea4eProtectedSqlite(path);
        try
        {
            var head = new Head {
                StoreId = storeId, Epoch = epoch, Generation = 0,
                StateHash = Hash(Schema + storeId +
                    epoch.ToString(CultureInfo.InvariantCulture)),
                TableHash = Ea4eNetworkGrantV4Digest.TableHash(
                    new Ea4eNetworkGrantV4Digest.Row[0]),
            };
            db.Execute("BEGIN IMMEDIATE");
            db.Execute(MetadataDdl);
            db.Execute(JournalDdl);
            db.Execute(RowsDdl);
            using (var insert = db.Prepare(
                "INSERT INTO network_grant_v4_metadata VALUES (?,?,?,?,?,?)"))
            {
                insert.BindText(1, Schema);
                insert.BindText(2, storeId);
                insert.BindText(3, epoch.ToString(CultureInfo.InvariantCulture));
                insert.BindText(4, "0");
                insert.BindText(5, head.StateHash);
                insert.BindText(6, head.TableHash);
                if (insert.Step()) throw new InvalidOperationException("Metadata insert denied");
            }
            db.Execute("COMMIT");
            WriteAnchor(anchorPrefix, head);
            return new Ea4eNetworkGrantV4Store(db, anchorPrefix, head);
        }
        catch { db.Dispose(); throw; }
    }

    internal static Ea4eNetworkGrantV4Store Open(string path, string anchorPrefix)
    {
        CheckPaths(path, anchorPrefix);
        if (!File.Exists(path)) throw new InvalidOperationException("Store missing");
        var db = new Ea4eProtectedSqlite(path);
        try
        {
            Head head = ReadHead(db);
            Verify(db, anchorPrefix, head);
            return new Ea4eNetworkGrantV4Store(db, anchorPrefix, head);
        }
        catch { db.Dispose(); throw; }
    }

    private void Transition(string operationHash, Action<Ea4eProtectedSqlite, Head> mutate,
                            bool failAfterCommitForTest)
    {
        if (operationHash == null || !Hex.IsMatch(operationHash) || mutate == null
            || generation >= 99999999)
            throw new InvalidOperationException("Transition denied");
        db.Execute("BEGIN IMMEDIATE");
        Head next;
        bool committed = false;
        try
        {
            Head current = ReadHead(db);
            if (current.StoreId != storeId || current.Epoch != epoch
                || current.Generation != generation || current.StateHash != stateHash)
                throw new InvalidOperationException("Concurrent store drift denied");
            Verify(db, anchorPrefix, current);
            mutate(db, current);
            string table = TableHash(db, current);
            string eventHash = Hash(operationHash + table);
            next = new Head {
                StoreId = storeId, Epoch = epoch, Generation = generation + 1,
                TableHash = table,
                StateHash = Hash(stateHash + eventHash +
                    (generation + 1).ToString("D20", CultureInfo.InvariantCulture)),
            };
            using (var insert = db.Prepare(
                "INSERT INTO network_grant_v4_journal VALUES (?,?,?,?,?,?)"))
            {
                insert.BindText(1, next.Generation.ToString(CultureInfo.InvariantCulture));
                insert.BindText(2, operationHash);
                insert.BindText(3, table);
                insert.BindText(4, eventHash);
                insert.BindText(5, stateHash);
                insert.BindText(6, next.StateHash);
                if (insert.Step()) throw new InvalidOperationException("Journal insert denied");
            }
            using (var update = db.Prepare(
                "UPDATE network_grant_v4_metadata SET generation=?,state_hash=?,table_hash=?"))
            {
                update.BindText(1, next.Generation.ToString(CultureInfo.InvariantCulture));
                update.BindText(2, next.StateHash);
                update.BindText(3, table);
                if (update.Step()) throw new InvalidOperationException("Metadata update denied");
            }
            db.Execute("COMMIT");
            committed = true;
        }
        catch
        {
            if (!committed) db.Execute("ROLLBACK");
            throw;
        }
        if (failAfterCommitForTest)
            throw new InvalidOperationException("Injected post-commit anchor gap");
        WriteAnchor(anchorPrefix, next);
        generation = next.Generation;
        stateHash = next.StateHash;
    }

    internal void IssueFake(byte[] artifact, IDictionary<string, string> expected,
                            IDictionary<string, string> labels,
                            bool failAfterCommitForTest = false)
    {
        if (artifact == null) throw new InvalidOperationException("Grant bytes denied");
        byte[] snapshot = (byte[])artifact.Clone();
        if (!Ea4eNetworkMutationGrantCandidate.MatchesComplete(snapshot, expected, labels))
            throw new InvalidOperationException("External expectation mismatch denied");
        var identity = Ea4eNetworkMutationGrantCandidate.ReadCompleteIdentity(snapshot);
        if (identity.StoreId != storeId || identity.StoreEpoch != epoch)
            throw new InvalidOperationException("Store identity mismatch denied");
        string json = Encoding.ASCII.GetString(snapshot);
        Transition(Hash("issue:" + identity.GrantId + ":" + Hash(json)),
            delegate(Ea4eProtectedSqlite store, Head head) {
                foreach (var row in ReadRows(store, head))
                {
                    var other = Ea4eNetworkMutationGrantCandidate.ReadCompleteIdentity(
                        row.ArtifactBytes());
                    if (other.GrantId == identity.GrantId || other.Nonce == identity.Nonce
                        || (other.AttemptId == identity.AttemptId
                            && other.Action == identity.Action)
                        || other.NetworkName == identity.NetworkName)
                        throw new InvalidOperationException("Duplicate grant identity denied");
                }
                using (var insert = store.Prepare(
                    "INSERT INTO network_grant_v4_rows VALUES (?,?,?)"))
                {
                    insert.BindText(1, identity.GrantId);
                    insert.BindText(2, json);
                    insert.BindText(3, "ISSUED");
                    if (insert.Step()) throw new InvalidOperationException("Grant insert denied");
                }
            }, failAfterCommitForTest);
    }

    private void ChangeFake(string grantId, string prior, string next, long now,
                            bool failAfterCommitForTest)
    {
        if (grantId == null || !Hex.IsMatch(grantId) || now < 1)
            throw new InvalidOperationException("Grant transition denied");
        Transition(Hash("state:" + grantId + ":" + prior + ":" + next),
            delegate(Ea4eProtectedSqlite store, Head head) {
                using (var read = store.Prepare(
                    "SELECT artifact_json,state FROM network_grant_v4_rows WHERE grant_id=?"))
                {
                    read.BindText(1, grantId);
                    if (!read.Step() || read.Text(1) != prior)
                        throw new InvalidOperationException("Grant prior state denied");
                    string artifact = read.Text(0);
                    var identity = Ea4eNetworkMutationGrantCandidate.ReadCompleteIdentity(
                        Encoding.ASCII.GetBytes(artifact));
                    if (identity.GrantId != grantId ||
                        (next == "CLAIMED" && now >= identity.ExpiresAt))
                        throw new InvalidOperationException("Grant expired or drifted");
                }
                using (var update = store.Prepare(
                    "UPDATE network_grant_v4_rows SET state=? WHERE grant_id=? AND state=?"))
                {
                    update.BindText(1, next);
                    update.BindText(2, grantId);
                    update.BindText(3, prior);
                    if (update.Step()) throw new InvalidOperationException("Grant update denied");
                }
            }, failAfterCommitForTest);
    }

    internal void ClaimFake(string grantId, long now)
    {
        ChangeFake(grantId, "ISSUED", "CLAIMED", now, false);
    }

    internal void RevokeFake(string grantId, long now)
    {
        ChangeFake(grantId, "ISSUED", "REVOKED", now, false);
    }

    internal void MarkUncertainFake(string grantId, long now)
    {
        ChangeFake(grantId, "CLAIMED", "UNCERTAIN", now, false);
    }

    public void Dispose() { db.Dispose(); }
}

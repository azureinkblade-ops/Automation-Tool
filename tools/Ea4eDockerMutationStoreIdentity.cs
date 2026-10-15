// Fake-qualified identity/rollback substrate; no authorization artifact or issuer.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

internal sealed class Ea4eDockerMutationStoreIdentity : IDisposable
{
    private const string Schema = "hermes.docker-mutation-store-identity/v3";
    private static readonly Regex Hex = new Regex(@"\A[0-9a-f]{64}\z");
    private readonly Ea4eProtectedSqlite db;
    private readonly string anchorPrefix;
    private readonly string storeId;
    private readonly int epoch;
    private int generation;
    private string stateHash;

    private sealed class Metadata
    {
        internal string StoreId;
        internal int Epoch;
        internal int Generation;
        internal string StateHash;
        internal string GrantDigest;
    }

    private Ea4eDockerMutationStoreIdentity(
        Ea4eProtectedSqlite db, string anchorPrefix, Metadata metadata)
    {
        this.db = db;
        this.anchorPrefix = anchorPrefix;
        storeId = metadata.StoreId;
        epoch = metadata.Epoch;
        generation = metadata.Generation;
        stateHash = metadata.StateHash;
    }

    private static string Hash(string value)
    {
        using (var sha = SHA256.Create())
        {
            byte[] bytes = sha.ComputeHash(Encoding.ASCII.GetBytes(value));
            return BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant();
        }
    }

    private static string GrantDigest(Ea4eProtectedSqlite db)
    {
        using (var sha = SHA256.Create())
        using (var stream = new MemoryStream())
        using (var writer = new BinaryWriter(stream, Encoding.UTF8))
        using (var read = db.Prepare(
            "SELECT grant_id,nonce,action,attempt_id,request_hash," +
            "predecessor_hash,source_commit,operator_sid,issued_at," +
            "expires_at,state FROM mutation_fake_grants ORDER BY grant_id"))
        {
            while (read.Step())
            {
                for (int column = 0; column < 11; column++)
                {
                    string value = read.Text(column);
                    if (value == null)
                        throw new InvalidOperationException("Grant row denied");
                    writer.Write(value);
                }
            }
            writer.Flush();
            return BitConverter.ToString(sha.ComputeHash(stream.ToArray()))
                .Replace("-", "").ToLowerInvariant();
        }
    }

    private static void CheckPaths(string path, string anchorPrefix)
    {
        if (String.IsNullOrWhiteSpace(path) || String.IsNullOrWhiteSpace(anchorPrefix)
            || !Path.IsPathRooted(path) || !Path.IsPathRooted(anchorPrefix)
            || String.Equals(Path.GetFullPath(path), Path.GetFullPath(anchorPrefix),
                             StringComparison.OrdinalIgnoreCase)
            || !Directory.Exists(Path.GetDirectoryName(path))
            || !Directory.Exists(Path.GetDirectoryName(anchorPrefix)))
            throw new InvalidOperationException("Store paths denied");
    }

    private static string AnchorPath(string prefix, int generation)
    {
        return prefix + ".g" + generation.ToString("D8", CultureInfo.InvariantCulture);
    }

    private static void WriteAnchor(string prefix, Metadata metadata)
    {
        using (var stream = new FileStream(
            AnchorPath(prefix, metadata.Generation), FileMode.CreateNew,
            FileAccess.Write, FileShare.None))
        using (var writer = new BinaryWriter(stream, Encoding.UTF8))
        {
            writer.Write(Schema);
            writer.Write(metadata.StoreId);
            writer.Write(metadata.Epoch);
            writer.Write(metadata.Generation);
            writer.Write(metadata.StateHash);
            writer.Write(metadata.GrantDigest);
            writer.Flush();
            stream.Flush(true);
        }
    }

    private static Metadata ReadAnchor(string path)
    {
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                                           FileShare.Read))
        using (var reader = new BinaryReader(stream, Encoding.UTF8))
        {
            if (stream.Length < 32 || stream.Length > 512)
                throw new InvalidOperationException("Anchor size denied");
            if (reader.ReadString() != Schema)
                throw new InvalidOperationException("Anchor schema denied");
            var metadata = new Metadata {
                StoreId = reader.ReadString(), Epoch = reader.ReadInt32(),
                Generation = reader.ReadInt32(), StateHash = reader.ReadString(),
                GrantDigest = reader.ReadString(),
            };
            if (stream.Position != stream.Length)
                throw new InvalidOperationException("Anchor trailing bytes denied");
            return metadata;
        }
    }

    private static Metadata ReadMetadata(Ea4eProtectedSqlite db)
    {
        using (var read = db.Prepare(
            "SELECT schema_id,store_id,epoch,generation,state_hash,grant_digest " +
            "FROM mutation_store_metadata"))
        {
            if (!read.Step() || read.Text(0) != Schema)
                throw new InvalidOperationException("Store schema denied");
            var metadata = new Metadata {
                StoreId = read.Text(1),
                Epoch = Int32.Parse(read.Text(2), CultureInfo.InvariantCulture),
                Generation = Int32.Parse(read.Text(3), CultureInfo.InvariantCulture),
                StateHash = read.Text(4),
                GrantDigest = read.Text(5),
            };
            if (read.Step() || !Hex.IsMatch(metadata.StoreId)
                || !Hex.IsMatch(metadata.StateHash)
                || !Hex.IsMatch(metadata.GrantDigest) || metadata.Epoch < 1
                || metadata.Generation < 0)
                throw new InvalidOperationException("Store metadata denied");
            return metadata;
        }
    }

    private static List<string> VerifyJournal(Ea4eProtectedSqlite db,
                                              Metadata metadata,
                                              out List<string> grantDigests)
    {
        string previous = Hash(Schema + metadata.StoreId +
            metadata.Epoch.ToString(CultureInfo.InvariantCulture));
        var states = new List<string> { previous };
        grantDigests = new List<string> { Hash("") };
        int count = 0;
        using (var read = db.Prepare(
            "SELECT generation,operation_hash,grant_digest,event_hash," +
            "prior_hash,state_hash " +
            "FROM mutation_store_journal ORDER BY generation"))
        {
            while (read.Step())
            {
                count++;
                string operationHash = read.Text(1);
                string grantDigest = read.Text(2);
                string eventHash = read.Text(3);
                string newHash = read.Text(5);
                if (read.Text(0) != count.ToString(CultureInfo.InvariantCulture)
                    || operationHash == null || !Hex.IsMatch(operationHash)
                    || grantDigest == null || !Hex.IsMatch(grantDigest)
                    || eventHash != Hash(operationHash + grantDigest)
                    || read.Text(4) != previous || newHash == null
                    || newHash != Hash(previous + eventHash +
                        count.ToString("D20", CultureInfo.InvariantCulture)))
                    throw new InvalidOperationException("Store journal denied");
                previous = newHash;
                states.Add(newHash);
                grantDigests.Add(grantDigest);
            }
        }
        if (count != metadata.Generation || previous != metadata.StateHash)
            throw new InvalidOperationException("Store journal head denied");
        if (grantDigests[count] != metadata.GrantDigest
            || GrantDigest(db) != metadata.GrantDigest)
            throw new InvalidOperationException("Grant rows drift denied");
        return states;
    }

    private static void VerifyAnchor(string prefix, Metadata metadata,
                                     IList<string> journalStates,
                                     IList<string> grantDigests)
    {
        string directory = Path.GetDirectoryName(prefix);
        string stem = Path.GetFileName(prefix) + ".g";
        int highest = -1;
        int count = 0;
        foreach (string file in Directory.GetFiles(directory, stem + "*"))
        {
            string suffix = Path.GetFileName(file).Substring(stem.Length);
            int candidate;
            if (suffix.Length != 8 || !Int32.TryParse(suffix,
                NumberStyles.None, CultureInfo.InvariantCulture, out candidate))
                throw new InvalidOperationException("Unexpected anchor file denied");
            highest = Math.Max(highest, candidate);
            count++;
        }
        if (highest != metadata.Generation || count != metadata.Generation + 1)
            throw new InvalidOperationException("Store anchor generation denied");
        for (int index = 0; index <= metadata.Generation; index++)
        {
            Metadata anchor = ReadAnchor(AnchorPath(prefix, index));
            if (anchor.StoreId != metadata.StoreId || anchor.Epoch != metadata.Epoch
                || anchor.Generation != index
                || anchor.StateHash != journalStates[index]
                || anchor.GrantDigest != grantDigests[index])
                throw new InvalidOperationException("Store anchor mismatch denied");
        }
    }

    internal static Ea4eDockerMutationStoreIdentity Initialize(
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
            var metadata = new Metadata {
                StoreId = storeId, Epoch = epoch, Generation = 0,
                StateHash = Hash(Schema + storeId +
                    epoch.ToString(CultureInfo.InvariantCulture)),
            };
            db.Execute("BEGIN IMMEDIATE");
            db.Execute("CREATE TABLE mutation_store_metadata (" +
                "schema_id TEXT NOT NULL,store_id TEXT NOT NULL,epoch TEXT NOT NULL," +
                "generation TEXT NOT NULL,state_hash TEXT NOT NULL," +
                "grant_digest TEXT NOT NULL)");
            db.Execute("CREATE TABLE mutation_store_journal (" +
                "generation INTEGER PRIMARY KEY,operation_hash TEXT NOT NULL," +
                "grant_digest TEXT NOT NULL,event_hash TEXT NOT NULL," +
                "prior_hash TEXT NOT NULL,state_hash TEXT NOT NULL)");
            db.Execute("CREATE TABLE mutation_fake_grants (" +
                "grant_id TEXT PRIMARY KEY,nonce TEXT NOT NULL UNIQUE," +
                "action TEXT NOT NULL,attempt_id TEXT NOT NULL," +
                "request_hash TEXT NOT NULL,predecessor_hash TEXT NOT NULL," +
                "source_commit TEXT NOT NULL,operator_sid TEXT NOT NULL," +
                "issued_at TEXT NOT NULL,expires_at TEXT NOT NULL," +
                "state TEXT NOT NULL,UNIQUE(attempt_id,action))");
            metadata.GrantDigest = GrantDigest(db);
            using (var insert = db.Prepare(
                "INSERT INTO mutation_store_metadata VALUES (?,?,?,?,?,?)"))
            {
                insert.BindText(1, Schema);
                insert.BindText(2, storeId);
                insert.BindText(3, epoch.ToString(CultureInfo.InvariantCulture));
                insert.BindText(4, "0");
                insert.BindText(5, metadata.StateHash);
                insert.BindText(6, metadata.GrantDigest);
                if (insert.Step())
                    throw new InvalidOperationException("Store insert denied");
            }
            db.Execute("COMMIT");
            WriteAnchor(anchorPrefix, metadata);
            return new Ea4eDockerMutationStoreIdentity(db, anchorPrefix, metadata);
        }
        catch
        {
            db.Dispose();
            throw;
        }
    }

    internal static Ea4eDockerMutationStoreIdentity Open(
        string path, string anchorPrefix)
    {
        CheckPaths(path, anchorPrefix);
        if (!File.Exists(path))
            throw new InvalidOperationException("Store missing");
        var db = new Ea4eProtectedSqlite(path);
        try
        {
            Metadata metadata = ReadMetadata(db);
            List<string> grantDigests;
            List<string> journalStates = VerifyJournal(db, metadata,
                                                       out grantDigests);
            VerifyAnchor(anchorPrefix, metadata, journalStates, grantDigests);
            return new Ea4eDockerMutationStoreIdentity(db, anchorPrefix, metadata);
        }
        catch
        {
            db.Dispose();
            throw;
        }
    }

    internal void RecordFakeEvent(string eventHash)
    {
        RecordFakeTransition(eventHash, delegate(Ea4eProtectedSqlite ignored) { });
    }

    // The caller's fixed-schema mutation and its journal generation commit together.
    internal void RecordFakeTransition(string eventHash,
                                       Action<Ea4eProtectedSqlite> mutation)
    {
        if (eventHash == null || !Hex.IsMatch(eventHash) || mutation == null
            || generation >= 99999999)
            throw new InvalidOperationException("Event hash denied");
        db.Execute("BEGIN IMMEDIATE");
        Metadata next;
        try
        {
            Metadata current = ReadMetadata(db);
            if (current.StoreId != storeId || current.Epoch != epoch
                || current.Generation != generation || current.StateHash != stateHash)
                throw new InvalidOperationException("Concurrent store drift denied");
            List<string> grantDigests;
            List<string> states = VerifyJournal(db, current, out grantDigests);
            VerifyAnchor(anchorPrefix, current, states, grantDigests);
            mutation(db);
            string grantDigest = GrantDigest(db);
            string boundEventHash = Hash(eventHash + grantDigest);
            next = new Metadata {
                StoreId = storeId, Epoch = epoch, Generation = generation + 1,
                GrantDigest = grantDigest,
                StateHash = Hash(stateHash + boundEventHash +
                    (generation + 1).ToString("D20", CultureInfo.InvariantCulture)),
            };
            using (var insert = db.Prepare(
                "INSERT INTO mutation_store_journal VALUES (?,?,?,?,?,?)"))
            {
                insert.BindText(1, next.Generation.ToString(CultureInfo.InvariantCulture));
                insert.BindText(2, eventHash);
                insert.BindText(3, grantDigest);
                insert.BindText(4, boundEventHash);
                insert.BindText(5, stateHash);
                insert.BindText(6, next.StateHash);
                if (insert.Step())
                    throw new InvalidOperationException("Journal insert denied");
            }
            using (var update = db.Prepare(
                "UPDATE mutation_store_metadata SET generation=?,state_hash=?," +
                "grant_digest=?"))
            {
                update.BindText(1, next.Generation.ToString(CultureInfo.InvariantCulture));
                update.BindText(2, next.StateHash);
                update.BindText(3, grantDigest);
                if (update.Step())
                    throw new InvalidOperationException("Metadata update denied");
            }
            db.Execute("COMMIT");
        }
        catch
        {
            db.Execute("ROLLBACK");
            throw;
        }
        WriteAnchor(anchorPrefix, next);
        generation = next.Generation;
        stateHash = next.StateHash;
    }

    public void Dispose()
    {
        db.Dispose();
    }
}

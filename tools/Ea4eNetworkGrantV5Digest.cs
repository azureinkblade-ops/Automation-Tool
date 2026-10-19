// Pure row/table digest; callers must validate candidate semantics separately.
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

internal static class Ea4eNetworkGrantV5Digest
{
    private const string Schema = "hermes.docker-network-grant-row/v5";
    private static readonly Regex Hex = new Regex(@"\A[0-9a-f]{64}\z");

    internal sealed class Row
    {
        internal readonly string GrantId;
        internal readonly string State;
        private readonly byte[] artifact;

        internal Row(string grantId, byte[] artifact, string state)
        {
            if (grantId == null || !Hex.IsMatch(grantId)
                || artifact == null || artifact.Length < 1 || artifact.Length > 16384
                || !IsState(state))
                throw new InvalidOperationException("Grant row denied");
            foreach (byte item in artifact)
                if (item < 0x20 || item > 0x7e)
                    throw new InvalidOperationException("Grant bytes denied");
            GrantId = grantId;
            this.artifact = (byte[])artifact.Clone();
            State = state;
        }

        internal byte[] ArtifactBytes()
        {
            return (byte[])artifact.Clone();
        }
    }

    private static bool IsState(string state)
    {
        return state == "ISSUED" || state == "CLAIMED"
            || state == "REVOKED" || state == "UNCERTAIN";
    }

    private static string Digest(byte[] bytes)
    {
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(bytes))
                .Replace("-", "").ToLowerInvariant();
    }

    internal static string RowHash(Row row)
    {
        if (row == null) throw new InvalidOperationException("Grant row missing");
        using (var stream = new MemoryStream())
        using (var writer = new BinaryWriter(stream, Encoding.UTF8))
        {
            byte[] artifact = row.ArtifactBytes();
            writer.Write(Schema);
            writer.Write(row.GrantId);
            writer.Write(artifact.Length);
            writer.Write(artifact);
            writer.Write(row.State);
            writer.Flush();
            return Digest(stream.ToArray());
        }
    }

    internal static string TableHash(IEnumerable<Row> rows)
    {
        if (rows == null) throw new InvalidOperationException("Grant rows missing");
        var ordered = new List<Row>(rows);
        ordered.Sort(delegate(Row left, Row right) {
            return StringComparer.Ordinal.Compare(left.GrantId, right.GrantId);
        });
        using (var stream = new MemoryStream())
        using (var writer = new BinaryWriter(stream, Encoding.UTF8))
        {
            writer.Write(Schema);
            writer.Write(ordered.Count);
            string previous = null;
            foreach (Row row in ordered)
            {
                if (row == null || String.Equals(previous, row.GrantId,
                                                  StringComparison.Ordinal))
                    throw new InvalidOperationException("Duplicate grant row denied");
                writer.Write(row.GrantId);
                writer.Write(RowHash(row));
                previous = row.GrantId;
            }
            writer.Flush();
            return Digest(stream.ToArray());
        }
    }
}

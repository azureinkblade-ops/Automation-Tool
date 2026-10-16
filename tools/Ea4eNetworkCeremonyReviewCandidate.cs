// Exact review data only. The caller must establish an operator-controlled source.
using System;
using System.Collections.Generic;
using System.Text;

internal static class Ea4eNetworkCeremonyReviewCandidate
{
    private static void AppendString(StringBuilder output, string value)
    {
        output.Append('"');
        foreach (char item in value)
        {
            if (item < 0x20 || item > 0x7e)
                throw new InvalidOperationException("Review text denied");
            if (item == '"' || item == '\\') output.Append('\\');
            output.Append(item);
        }
        output.Append('"');
    }

    internal static bool Matches(byte[] reviewBytes, byte[] requestBytes,
        byte[] grantBytes, IDictionary<string, string> expectedGrant,
        IDictionary<string, string> expectedLabels)
    {
        if (reviewBytes == null || reviewBytes.Length < 1 || reviewBytes.Length > 16384
            || !Ea4eNetworkRequestGrantBinding.Matches(
                requestBytes, grantBytes, expectedGrant, expectedLabels))
            return false;
        try
        {
            var values = new SortedDictionary<string, string>(StringComparer.Ordinal) {
                { "action", "network_create" },
                { "attempt_id", expectedGrant["attempt_id"] },
                { "authority_id", expectedGrant["authority_id"] },
                { "ceremony_id", expectedGrant["ceremony_id"] },
                { "docker_executable_sha256", expectedGrant["docker_executable_sha256"] },
                { "expires_at", expectedGrant["expires_at"] },
                { "grant_artifact_hash", expectedGrant["artifact_hash"] },
                { "grant_id", expectedGrant["grant_id"] },
                { "issuer_binary_sha256", expectedGrant["issuer_binary_sha256"] },
                { "issued_at", expectedGrant["issued_at"] },
                { "network_name", expectedGrant["network_name"] },
                { "nonce", expectedGrant["nonce"] },
                { "operator_sid", expectedGrant["operator_sid"] },
                { "predecessor_hash", expectedGrant["predecessor_hash"] },
                { "request_hash", expectedGrant["request_hash"] },
                { "schema_id", "hermes.docker-network-ceremony-review-candidate/v1" },
                { "source_commit", expectedGrant["source_commit"] },
                { "store_epoch", expectedGrant["store_epoch"] },
                { "store_id", expectedGrant["store_id"] },
            };
            var canonical = new StringBuilder("{");
            foreach (var pair in values)
            {
                if (canonical.Length > 1) canonical.Append(',');
                AppendString(canonical, pair.Key);
                canonical.Append(':');
                AppendString(canonical, pair.Value);
            }
            canonical.Append('}');
            byte[] expected = Encoding.UTF8.GetBytes(canonical.ToString());
            if (reviewBytes.Length != expected.Length) return false;
            for (int index = 0; index < expected.Length; index++)
                if (reviewBytes[index] != expected[index]) return false;
            return true;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return false;
        }
    }
}

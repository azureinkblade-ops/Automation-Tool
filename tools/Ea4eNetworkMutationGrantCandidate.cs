// Pure byte check for a network-create grant candidate. This does not issue authority.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

internal static class Ea4eNetworkMutationGrantCandidate
{
    private static readonly Regex Hex = new Regex(@"\A[0-9a-f]{64}\z");
    private static readonly Regex Network = new Regex(@"\Aea4e-kilo-[0-9a-f]{32}\z");
    private static readonly Regex Attempt = new Regex(@"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\z");
    private static readonly Regex Sid = new Regex(@"\AS-[0-9]+(?:-[0-9]+)+\z");
    private static readonly HashSet<string> Fields = new HashSet<string> {
        "schema_id", "action", "grant_id", "nonce", "store_id", "store_epoch",
        "attempt_id", "request_hash", "predecessor_hash", "source_commit",
        "operator_sid", "docker_executable_sha256", "docker_engine_endpoint",
        "network_name", "issued_at", "expires_at", "artifact_hash",
    };
    private static readonly HashSet<string> ExpectedFields = new HashSet<string> {
        "grant_id", "nonce", "store_id", "store_epoch", "attempt_id",
        "request_hash", "predecessor_hash", "source_commit", "operator_sid",
        "docker_executable_sha256", "network_name", "issued_at", "expires_at",
        "artifact_hash",
    };

    private static void AppendString(StringBuilder output, string value)
    {
        output.Append('"');
        foreach (char item in value)
        {
            if (item < 0x20 || item > 0x7e)
                throw new InvalidOperationException("Non-ASCII grant denied");
            if (item == '"' || item == '\\') output.Append('\\');
            output.Append(item);
        }
        output.Append('"');
    }

    private static void AppendCanonical(StringBuilder output, object value)
    {
        var map = value as IDictionary<string, object>;
        if (map != null)
        {
            var keys = new List<string>(map.Keys);
            keys.Sort(StringComparer.Ordinal);
            output.Append('{');
            for (int index = 0; index < keys.Count; index++)
            {
                if (index > 0) output.Append(',');
                AppendString(output, keys[index]);
                output.Append(':');
                AppendCanonical(output, map[keys[index]]);
            }
            output.Append('}');
        }
        else if (value is string) AppendString(output, (string)value);
        else if (value is int)
            output.Append(((int)value).ToString(CultureInfo.InvariantCulture));
        else if (value is long)
            output.Append(((long)value).ToString(CultureInfo.InvariantCulture));
        else throw new InvalidOperationException("Grant value denied");
    }

    private static string Canonical(object value)
    {
        var output = new StringBuilder();
        AppendCanonical(output, value);
        return output.ToString();
    }

    private static long Number(object value)
    {
        if (value is int) return (int)value;
        if (value is long) return (long)value;
        throw new InvalidOperationException("Grant number denied");
    }

    internal static bool Matches(byte[] raw, IDictionary<string, string> expected)
    {
        if (raw == null || raw.Length < 1 || raw.Length > 16384
            || expected == null || expected.Count != ExpectedFields.Count
            || !ExpectedFields.SetEquals(expected.Keys))
            return false;
        try
        {
            foreach (string key in ExpectedFields)
                if (!expected.ContainsKey(key) || String.IsNullOrEmpty(expected[key]))
                    return false;
            string json = new UTF8Encoding(false, true).GetString(raw);
            var parser = new JavaScriptSerializer {
                MaxJsonLength = 16384, RecursionLimit = 4,
            };
            var grant = parser.DeserializeObject(json) as IDictionary<string, object>;
            if (grant == null || grant.Count != Fields.Count
                || !Fields.SetEquals(grant.Keys) || Canonical(grant) != json)
                return false;
            if (!Equals(grant["schema_id"],
                        "hermes.docker-network-mutation-grant-candidate/v1")
                || !Equals(grant["action"], "network_create")
                || !Equals(grant["docker_engine_endpoint"],
                           "npipe:////./pipe/dockerDesktopLinuxEngine"))
                return false;
            foreach (string key in new[] { "grant_id", "nonce", "store_id",
                "request_hash", "predecessor_hash", "source_commit",
                "docker_executable_sha256", "artifact_hash" })
                if (!(grant[key] is string) || !Hex.IsMatch((string)grant[key]))
                    return false;
            if (!(grant["attempt_id"] is string)
                || !Attempt.IsMatch((string)grant["attempt_id"])
                || !(grant["operator_sid"] is string)
                || !Sid.IsMatch((string)grant["operator_sid"])
                || !(grant["network_name"] is string)
                || !Network.IsMatch((string)grant["network_name"]))
                return false;
            long epoch = Number(grant["store_epoch"]);
            long issued = Number(grant["issued_at"]);
            long expiry = Number(grant["expires_at"]);
            if (epoch < 1 || epoch > Int32.MaxValue || issued < 1
                || expiry <= issued || expiry - issued > 300)
                return false;
            foreach (var pair in expected)
            {
                object value = grant[pair.Key];
                string actual = value is string ? (string)value
                    : Number(value).ToString(CultureInfo.InvariantCulture);
                if (!String.Equals(actual, pair.Value, StringComparison.Ordinal))
                    return false;
            }
            var payload = new Dictionary<string, object>(grant);
            payload.Remove("artifact_hash");
            using (var sha = SHA256.Create())
            {
                string digest = BitConverter.ToString(
                    sha.ComputeHash(Encoding.UTF8.GetBytes(Canonical(payload))))
                    .Replace("-", "").ToLowerInvariant();
                return Equals(grant["artifact_hash"], digest);
            }
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return false;
        }
    }
}

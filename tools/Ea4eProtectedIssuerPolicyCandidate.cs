// Pure policy-byte validation. The expected hash must come from outside the app.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

internal static class Ea4eProtectedIssuerPolicyCandidate
{
    private const string Schema = "hermes.ea4e.protected-issuer-policy/v1";
    private const string Profile = "LOCAL_CONTAINER_PROTECTED_ISSUER";
    private const string Endpoint = "npipe:////./pipe/dockerDesktopLinuxEngine";
    private static readonly Regex Hex = new Regex(@"\A[0-9a-f]{64}\z");
    private static readonly Regex Sid = new Regex(@"\AS-[0-9]+(?:-[0-9]+){2,}\z");
    private static readonly Regex Version = new Regex(@"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\z");
    private static readonly HashSet<string> Fields = new HashSet<string> {
        "schema_id", "profile", "action", "installation_version",
        "issuer_path", "issuer_sha256", "dependency_manifest_path",
        "dependency_manifest_hash",
        "policy_path", "operator_sid", "app_sid", "governing_commit",
        "authority_id", "store_path", "anchor_prefix", "store_id",
        "store_epoch", "docker_executable_path", "docker_executable_sha256",
        "docker_engine_endpoint", "max_ttl_seconds", "one_attempt_budget",
    };
    private static readonly string[] HashFields = {
        "issuer_sha256", "dependency_manifest_hash", "governing_commit",
        "authority_id", "store_id", "docker_executable_sha256",
    };
    private static readonly string[] PathFields = {
        "issuer_path", "dependency_manifest_path", "policy_path",
        "store_path", "anchor_prefix",
        "docker_executable_path",
    };

    internal sealed class Policy
    {
        private readonly IDictionary<string, object> values;
        internal readonly string Sha256;

        internal Policy(IDictionary<string, object> values, string sha256)
        {
            this.values = new Dictionary<string, object>(values);
            Sha256 = sha256;
        }

        internal string Text(string key) { return (string)values[key]; }
        internal int Number(string key) { return Convert.ToInt32(values[key]); }
    }

    private static void AppendString(StringBuilder output, string value)
    {
        output.Append('"');
        foreach (char item in value)
        {
            if (item < 0x20 || item > 0x7e)
                throw new InvalidOperationException("Policy ASCII denied");
            if (item == '"' || item == '\\') output.Append('\\');
            output.Append(item);
        }
        output.Append('"');
    }

    private static string Canonical(IDictionary<string, object> values)
    {
        var output = new StringBuilder();
        var keys = new List<string>(values.Keys);
        keys.Sort(StringComparer.Ordinal);
        output.Append('{');
        for (int index = 0; index < keys.Count; index++)
        {
            if (index > 0) output.Append(',');
            AppendString(output, keys[index]);
            output.Append(':');
            object value = values[keys[index]];
            if (value is string) AppendString(output, (string)value);
            else if (value is int)
                output.Append(((int)value).ToString(CultureInfo.InvariantCulture));
            else throw new InvalidOperationException("Policy value denied");
        }
        output.Append('}');
        return output.ToString();
    }

    private static bool CanonicalLocalPath(string value)
    {
        if (String.IsNullOrEmpty(value) || value.Length > 32767
            || value.Length < 4 || !Char.IsLetter(value[0]) || value[1] != ':'
            || value[2] != '\\' || value.IndexOf(':', 2) >= 0
            || value.IndexOf('/') >= 0 || value.EndsWith("\\", StringComparison.Ordinal))
            return false;
        try
        {
            return String.Equals(Path.GetFullPath(value), value,
                                 StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    }

    internal static Policy Read(byte[] raw, string independentlyExpectedHash)
    {
        if (raw == null || raw.Length < 1 || raw.Length > 16384
            || independentlyExpectedHash == null || !Hex.IsMatch(independentlyExpectedHash))
            throw new InvalidOperationException("Policy input denied");
        try
        {
            string json = new UTF8Encoding(false, true).GetString(raw);
            var parser = new JavaScriptSerializer {
                MaxJsonLength = 16384, RecursionLimit = 2,
            };
            var values = parser.DeserializeObject(json) as IDictionary<string, object>;
            if (values == null || values.Count != Fields.Count
                || !Fields.SetEquals(values.Keys) || Canonical(values) != json)
                throw new InvalidOperationException("Policy fields denied");
            using (var sha = SHA256.Create())
            {
                string digest = BitConverter.ToString(sha.ComputeHash(raw))
                    .Replace("-", "").ToLowerInvariant();
                if (!String.Equals(digest, independentlyExpectedHash,
                                   StringComparison.Ordinal))
                    throw new InvalidOperationException("Policy hash denied");
            }
            if (!Equals(values["schema_id"], Schema)
                || !Equals(values["profile"], Profile)
                || !Equals(values["action"], "network_create")
                || !Equals(values["docker_engine_endpoint"], Endpoint)
                || !(values["installation_version"] is string)
                || !Version.IsMatch((string)values["installation_version"]))
                throw new InvalidOperationException("Policy scope denied");
            foreach (string key in HashFields)
                if (!(values[key] is string) || !Hex.IsMatch((string)values[key]))
                    throw new InvalidOperationException("Policy identity denied");
            foreach (string key in PathFields)
                if (!(values[key] is string)
                    || !CanonicalLocalPath((string)values[key]))
                    throw new InvalidOperationException("Policy path denied");
            string install = Path.GetDirectoryName((string)values["issuer_path"]);
            if (!String.Equals(install,
                    Path.GetDirectoryName((string)values["policy_path"]),
                    StringComparison.OrdinalIgnoreCase)
                || !String.Equals(install,
                    Path.GetDirectoryName((string)values["dependency_manifest_path"]),
                    StringComparison.OrdinalIgnoreCase)
                || !String.Equals(
                    Path.GetDirectoryName((string)values["store_path"]),
                    Path.GetDirectoryName((string)values["anchor_prefix"]),
                    StringComparison.OrdinalIgnoreCase)
                || String.Equals((string)values["issuer_path"],
                    (string)values["policy_path"], StringComparison.OrdinalIgnoreCase)
                || String.Equals((string)values["issuer_path"],
                    (string)values["dependency_manifest_path"],
                    StringComparison.OrdinalIgnoreCase)
                || String.Equals((string)values["policy_path"],
                    (string)values["dependency_manifest_path"],
                    StringComparison.OrdinalIgnoreCase)
                || String.Equals((string)values["store_path"],
                    (string)values["anchor_prefix"], StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Policy placement denied");
            foreach (string key in new[] { "operator_sid", "app_sid" })
                if (!(values[key] is string) || !Sid.IsMatch((string)values[key]))
                    throw new InvalidOperationException("Policy SID denied");
            if (!(values["store_epoch"] is int) || (int)values["store_epoch"] < 1
                || !(values["max_ttl_seconds"] is int)
                || (int)values["max_ttl_seconds"] < 1
                || (int)values["max_ttl_seconds"] > 300
                || !(values["one_attempt_budget"] is int)
                || (int)values["one_attempt_budget"] != 1)
                throw new InvalidOperationException("Policy budget denied");
            return new Policy(values, independentlyExpectedHash);
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            throw new InvalidOperationException("Policy denied", error);
        }
    }
}

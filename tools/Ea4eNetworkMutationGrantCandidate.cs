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
    private static readonly Regex Owner = new Regex(@"\Aea4e-kilo-owner-[0-9a-f]{32}\z");
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
    private static readonly HashSet<string> CompleteFields = new HashSet<string> {
        "schema_id", "action", "grant_id", "nonce", "issuer_binary_sha256",
        "ceremony_id", "store_id", "store_epoch", "attempt_id", "authority_id",
        "request_hash", "predecessor_hash", "source_commit", "operator_sid",
        "docker_executable_sha256", "docker_engine_endpoint", "network_name",
        "network_driver", "network_internal", "labels", "command_spec_hash",
        "issued_at", "expires_at", "one_attempt_budget", "state_at_issue",
        "artifact_hash",
    };
    private static readonly HashSet<string> CompleteExpectedFields = new HashSet<string> {
        "grant_id", "nonce", "issuer_binary_sha256", "ceremony_id", "store_id",
        "store_epoch", "attempt_id", "authority_id", "request_hash",
        "predecessor_hash", "source_commit", "operator_sid",
        "docker_executable_sha256", "network_name", "issued_at", "expires_at",
        "artifact_hash",
    };
    private static readonly HashSet<string> LabelKeys = new HashSet<string> {
        "hermes.ea4e.attempt", "hermes.ea4e.candidate_sha256",
        "hermes.ea4e.profile", "hermes.ea4e.cleanup_owner",
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
        else if (value is bool) output.Append((bool)value ? "true" : "false");
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

    internal sealed class CompleteIdentity
    {
        internal readonly string GrantId;
        internal readonly string Nonce;
        internal readonly string AttemptId;
        internal readonly string Action;
        internal readonly string NetworkName;

        internal CompleteIdentity(IDictionary<string, object> grant)
        {
            GrantId = (string)grant["grant_id"];
            Nonce = (string)grant["nonce"];
            AttemptId = (string)grant["attempt_id"];
            Action = (string)grant["action"];
            NetworkName = (string)grant["network_name"];
        }
    }

    // Internal consistency only. Callers must separately bind trusted expectations.
    internal static CompleteIdentity ReadCompleteIdentity(byte[] raw)
    {
        if (raw == null || raw.Length < 1 || raw.Length > 16384)
            throw new InvalidOperationException("Grant bytes denied");
        try
        {
            string json = new UTF8Encoding(false, true).GetString(raw);
            var parser = new JavaScriptSerializer {
                MaxJsonLength = 16384, RecursionLimit = 5,
            };
            var grant = parser.DeserializeObject(json) as IDictionary<string, object>;
            if (grant == null || grant.Count != CompleteFields.Count
                || !CompleteFields.SetEquals(grant.Keys))
                throw new InvalidOperationException("Grant fields denied");
            var expected = new Dictionary<string, string>();
            foreach (string key in CompleteExpectedFields)
            {
                object value = grant[key];
                expected.Add(key, value is string ? (string)value
                    : Number(value).ToString(CultureInfo.InvariantCulture));
            }
            var rawLabels = grant["labels"] as IDictionary<string, object>;
            if (rawLabels == null || rawLabels.Count != LabelKeys.Count
                || !LabelKeys.SetEquals(rawLabels.Keys))
                throw new InvalidOperationException("Grant labels denied");
            var labels = new Dictionary<string, string>();
            foreach (string key in LabelKeys)
                labels.Add(key, rawLabels[key] as string);
            if (!MatchesComplete(raw, expected, labels))
                throw new InvalidOperationException("Grant structure denied");
            return new CompleteIdentity(grant);
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            throw new InvalidOperationException("Grant identity denied", error);
        }
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

    internal static bool MatchesComplete(byte[] raw,
        IDictionary<string, string> expected,
        IDictionary<string, string> expectedLabels)
    {
        if (raw == null || raw.Length < 1 || raw.Length > 16384
            || expected == null || expected.Count != CompleteExpectedFields.Count
            || !CompleteExpectedFields.SetEquals(expected.Keys)
            || expectedLabels == null || expectedLabels.Count != LabelKeys.Count
            || !LabelKeys.SetEquals(expectedLabels.Keys))
            return false;
        try
        {
            foreach (string key in CompleteExpectedFields)
                if (String.IsNullOrEmpty(expected[key])) return false;
            foreach (string key in LabelKeys)
                if (String.IsNullOrEmpty(expectedLabels[key])) return false;
            string json = new UTF8Encoding(false, true).GetString(raw);
            var parser = new JavaScriptSerializer {
                MaxJsonLength = 16384, RecursionLimit = 5,
            };
            var grant = parser.DeserializeObject(json) as IDictionary<string, object>;
            if (grant == null || grant.Count != CompleteFields.Count
                || !CompleteFields.SetEquals(grant.Keys) || Canonical(grant) != json)
                return false;
            if (!Equals(grant["schema_id"],
                        "hermes.docker-network-mutation-grant-candidate/v2")
                || !Equals(grant["action"], "network_create")
                || !Equals(grant["docker_engine_endpoint"],
                           "npipe:////./pipe/dockerDesktopLinuxEngine")
                || !Equals(grant["network_driver"], "bridge")
                || !Equals(grant["network_internal"], true)
                || !Equals(grant["state_at_issue"], "ISSUED")
                || Number(grant["one_attempt_budget"]) != 1)
                return false;
            foreach (string key in new[] { "grant_id", "nonce", "issuer_binary_sha256",
                "ceremony_id", "store_id", "authority_id", "request_hash",
                "predecessor_hash", "source_commit", "docker_executable_sha256",
                "command_spec_hash", "artifact_hash" })
                if (!(grant[key] is string) || !Hex.IsMatch((string)grant[key]))
                    return false;
            if (!(grant["attempt_id"] is string)
                || !Attempt.IsMatch((string)grant["attempt_id"])
                || !(grant["operator_sid"] is string)
                || !Sid.IsMatch((string)grant["operator_sid"])
                || !(grant["network_name"] is string)
                || !Network.IsMatch((string)grant["network_name"])
                || !Equals(grant["command_spec_hash"], grant["request_hash"]))
                return false;
            long epoch = Number(grant["store_epoch"]);
            long issued = Number(grant["issued_at"]);
            long expiry = Number(grant["expires_at"]);
            if (epoch < 1 || epoch > Int32.MaxValue || issued < 1
                || expiry <= issued || expiry - issued > 300)
                return false;
            var labels = grant["labels"] as IDictionary<string, object>;
            if (labels == null || labels.Count != LabelKeys.Count
                || !LabelKeys.SetEquals(labels.Keys))
                return false;
            foreach (string key in LabelKeys)
                if (!Equals(labels[key], expectedLabels[key])) return false;
            if (!Equals(labels["hermes.ea4e.attempt"], grant["attempt_id"])
                || !(labels["hermes.ea4e.candidate_sha256"] is string)
                || !Hex.IsMatch((string)labels["hermes.ea4e.candidate_sha256"])
                || !Equals(labels["hermes.ea4e.profile"],
                           "FAKE_ONLY_LOCAL_CONTAINER")
                || !(labels["hermes.ea4e.cleanup_owner"] is string)
                || !Owner.IsMatch((string)labels["hermes.ea4e.cleanup_owner"]))
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

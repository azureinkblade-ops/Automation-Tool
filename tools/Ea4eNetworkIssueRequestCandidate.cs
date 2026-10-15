// Pure candidate-data check. A match is not an operator witness or permit.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

internal static class Ea4eNetworkIssueRequestCandidate
{
    private static readonly Regex Hex = new Regex(@"\A[0-9a-f]{64}\z");
    private static readonly Regex Network = new Regex(@"\Aea4e-kilo-[0-9a-f]{32}\z");
    private static readonly Regex Owner = new Regex(@"\Aea4e-kilo-owner-[0-9a-f]{32}\z");
    private static readonly HashSet<string> Fields = new HashSet<string> {
        "schema_id", "action", "attempt_id", "intent_hash", "candidate_hash",
        "spec_hash", "governing_commit", "docker_executable_sha256",
        "docker_engine_endpoint", "network_name", "network_driver",
        "network_internal", "labels", "argv", "operator_id", "nonce",
        "requested_ttl_seconds", "operator_verified", "issue_authorized",
        "create_authorized", "launch_authorized", "request_hash",
    };
    private static readonly HashSet<string> LabelKeys = new HashSet<string> {
        "hermes.ea4e.attempt", "hermes.ea4e.candidate_sha256",
        "hermes.ea4e.profile", "hermes.ea4e.cleanup_owner",
    };

    private static string Digest(string value)
    {
        using (var sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(value)))
                .Replace("-", "").ToLowerInvariant();
    }

    private static void AppendString(StringBuilder output, string value)
    {
        output.Append('"');
        foreach (char item in value)
        {
            if (item < 0x20 || item > 0x7e)
                throw new InvalidOperationException("Non-ASCII request denied");
            if (item == '"' || item == '\\')
                output.Append('\\');
            output.Append(item);
        }
        output.Append('"');
    }

    private static void AppendCanonical(StringBuilder output, object value)
    {
        var map = value as IDictionary<string, object>;
        if (map != null)
        {
            output.Append('{');
            var keys = new List<string>(map.Keys);
            keys.Sort(StringComparer.Ordinal);
            for (int index = 0; index < keys.Count; index++)
            {
                if (index > 0) output.Append(',');
                AppendString(output, keys[index]);
                output.Append(':');
                AppendCanonical(output, map[keys[index]]);
            }
            output.Append('}');
        }
        else if (value is string)
            AppendString(output, (string)value);
        else if (value is bool)
            output.Append((bool)value ? "true" : "false");
        else if (value is int)
            output.Append(((int)value).ToString(System.Globalization.CultureInfo.InvariantCulture));
        else if (value is IList)
        {
            var list = (IList)value;
            output.Append('[');
            for (int index = 0; index < list.Count; index++)
            {
                if (index > 0) output.Append(',');
                AppendCanonical(output, list[index]);
            }
            output.Append(']');
        }
        else
            throw new InvalidOperationException("Request value denied");
    }

    private static string Canonical(object value)
    {
        var output = new StringBuilder();
        AppendCanonical(output, value);
        return output.ToString();
    }

    private static bool IsText(object value)
    {
        return value is string && !String.IsNullOrEmpty((string)value);
    }

    internal static bool Matches(byte[] raw, string expectedHash,
        string expectedCommit, string expectedDockerHash, string expectedAttempt,
        string expectedOperator, string expectedNetwork,
        IDictionary<string, string> expectedLabels)
    {
        if (raw == null || raw.Length == 0 || raw.Length > 16384
            || expectedHash == null || !Hex.IsMatch(expectedHash)
            || expectedCommit == null || !Hex.IsMatch(expectedCommit)
            || expectedDockerHash == null || !Hex.IsMatch(expectedDockerHash)
            || String.IsNullOrEmpty(expectedAttempt)
            || String.IsNullOrEmpty(expectedOperator)
            || expectedNetwork == null || !Network.IsMatch(expectedNetwork)
            || expectedLabels == null || expectedLabels.Count != LabelKeys.Count)
            return false;
        try
        {
            foreach (string key in LabelKeys)
                if (!expectedLabels.ContainsKey(key) || !IsText(expectedLabels[key]))
                    return false;
            string json = new UTF8Encoding(false, true).GetString(raw);
            var parser = new JavaScriptSerializer {
                MaxJsonLength = 16384, RecursionLimit = 8,
            };
            var request = parser.DeserializeObject(json) as IDictionary<string, object>;
            if (request == null || request.Count != Fields.Count
                || !Fields.SetEquals(request.Keys) || Canonical(request) != json)
                return false;
            if (!Equals(request["schema_id"],
                        "hermes.agent-local-kilo-network-issue-request/v1")
                || !Equals(request["action"], "network_create")
                || !Equals(request["docker_engine_endpoint"],
                           "npipe:////./pipe/dockerDesktopLinuxEngine")
                || !Equals(request["network_driver"], "bridge")
                || !Equals(request["network_internal"], true))
                return false;
            foreach (string flag in new[] { "operator_verified", "issue_authorized",
                                           "create_authorized", "launch_authorized" })
                if (!Equals(request[flag], false)) return false;
            foreach (string field in new[] { "intent_hash", "candidate_hash", "spec_hash" })
                if (!IsText(request[field]) || !Hex.IsMatch((string)request[field]))
                    return false;
            if (!Equals(request["governing_commit"], expectedCommit)
                || !Equals(request["docker_executable_sha256"], expectedDockerHash)
                || !Equals(request["attempt_id"], expectedAttempt)
                || !Equals(request["operator_id"], expectedOperator)
                || !Equals(request["network_name"], expectedNetwork)
                || !IsText(request["nonce"])
                || !(request["requested_ttl_seconds"] is int)
                || (int)request["requested_ttl_seconds"] < 1
                || (int)request["requested_ttl_seconds"] > 300)
                return false;
            if (!Equals(expectedLabels["hermes.ea4e.attempt"], expectedAttempt)
                || !Equals(expectedLabels["hermes.ea4e.candidate_sha256"],
                           request["candidate_hash"])
                || !Equals(expectedLabels["hermes.ea4e.profile"],
                           "FAKE_ONLY_LOCAL_CONTAINER")
                || !Owner.IsMatch(expectedLabels["hermes.ea4e.cleanup_owner"]))
                return false;
            var labels = request["labels"] as IDictionary<string, object>;
            if (labels == null || labels.Count != LabelKeys.Count
                || !LabelKeys.SetEquals(labels.Keys))
                return false;
            foreach (string key in LabelKeys)
                if (!Equals(labels[key], expectedLabels[key])) return false;
            var expectedArgv = new List<string> {
                "network", "create", "--driver", "bridge", "--internal",
            };
            var labelNames = new List<string>(LabelKeys);
            labelNames.Sort(StringComparer.Ordinal);
            foreach (string key in labelNames)
            {
                expectedArgv.Add("--label");
                expectedArgv.Add(key + "=" + expectedLabels[key]);
            }
            expectedArgv.Add(expectedNetwork);
            var argv = request["argv"] as IList;
            if (argv == null || argv.Count != expectedArgv.Count)
                return false;
            for (int index = 0; index < argv.Count; index++)
                if (!Equals(argv[index], expectedArgv[index])) return false;
            if (!IsText(request["request_hash"])) return false;
            var payload = new Dictionary<string, object>(request);
            payload.Remove("request_hash");
            string digest = Digest(Canonical(payload));
            return Equals(request["request_hash"], digest) && digest == expectedHash;
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return false;
        }
    }
}

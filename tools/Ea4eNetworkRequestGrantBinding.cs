// Pure relationship check; neither input nor a match confers authority.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Web.Script.Serialization;

internal static class Ea4eNetworkRequestGrantBinding
{
    internal static bool Matches(byte[] requestBytes, byte[] grantBytes,
        IDictionary<string, string> expectedGrant,
        IDictionary<string, string> expectedLabels)
    {
        if (requestBytes == null || grantBytes == null || expectedGrant == null
            || expectedLabels == null
            || !Ea4eNetworkMutationGrantCandidate.MatchesComplete(
                grantBytes, expectedGrant, expectedLabels))
            return false;
        try
        {
            if (!Ea4eNetworkIssueRequestCandidate.Matches(
                requestBytes, expectedGrant["request_hash"],
                expectedGrant["source_commit"],
                expectedGrant["docker_executable_sha256"],
                expectedGrant["attempt_id"], expectedGrant["operator_sid"],
                expectedGrant["network_name"], expectedLabels))
                return false;
            var request = new JavaScriptSerializer {
                MaxJsonLength = 16384, RecursionLimit = 8,
            }.DeserializeObject(new UTF8Encoding(false, true).GetString(requestBytes))
                as IDictionary<string, object>;
            if (request == null || !(request["requested_ttl_seconds"] is int))
                return false;
            long issued = Int64.Parse(expectedGrant["issued_at"],
                                      NumberStyles.None, CultureInfo.InvariantCulture);
            long expires = Int64.Parse(expectedGrant["expires_at"],
                                       NumberStyles.None, CultureInfo.InvariantCulture);
            return expires - issued <= (int)request["requested_ttl_seconds"];
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return false;
        }
    }
}

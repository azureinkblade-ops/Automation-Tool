using System;
using System.Collections.Generic;
using System.IO;

internal static class Ea4eNetworkGrantProbe
{
    private static readonly string[] Keys = {
        "grant_id", "nonce", "store_id", "store_epoch", "attempt_id",
        "request_hash", "predecessor_hash", "source_commit", "operator_sid",
        "docker_executable_sha256", "network_name", "issued_at", "expires_at",
        "artifact_hash",
    };

    private static int Main(string[] args)
    {
        if (args.Length != Keys.Length + 1) return 2;
        var expected = new Dictionary<string, string>();
        for (int index = 0; index < Keys.Length; index++)
            expected.Add(Keys[index], args[index + 1]);
        bool matches = Ea4eNetworkMutationGrantCandidate.Matches(
            File.ReadAllBytes(args[0]), expected);
        Console.WriteLine(matches ? "MATCH:NON_AUTHORIZING_CANDIDATE" : "DENY");
        return matches ? 0 : 1;
    }
}

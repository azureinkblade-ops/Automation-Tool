using System;
using System.Collections.Generic;
using System.IO;

internal static class Ea4eNetworkRequestGrantBindingProbe
{
    private static readonly string[] GrantKeys = {
        "grant_id", "nonce", "issuer_binary_sha256", "ceremony_id", "store_id",
        "store_epoch", "attempt_id", "authority_id", "request_hash",
        "predecessor_hash", "source_commit", "operator_sid",
        "docker_executable_sha256", "network_name", "issued_at", "expires_at",
        "artifact_hash",
    };
    private static readonly string[] LabelKeys = {
        "hermes.ea4e.attempt", "hermes.ea4e.candidate_sha256",
        "hermes.ea4e.profile", "hermes.ea4e.cleanup_owner",
    };

    private static int Main(string[] args)
    {
        if (args.Length != 2 + GrantKeys.Length + LabelKeys.Length) return 2;
        var expected = new Dictionary<string, string>();
        var labels = new Dictionary<string, string>();
        for (int index = 0; index < GrantKeys.Length; index++)
            expected.Add(GrantKeys[index], args[index + 2]);
        for (int index = 0; index < LabelKeys.Length; index++)
            labels.Add(LabelKeys[index], args[index + 2 + GrantKeys.Length]);
        bool matches = Ea4eNetworkRequestGrantBinding.Matches(
            File.ReadAllBytes(args[0]), File.ReadAllBytes(args[1]), expected, labels);
        Console.WriteLine(matches ? "MATCH:NON_AUTHORIZING_BINDING" : "DENY");
        return matches ? 0 : 1;
    }
}

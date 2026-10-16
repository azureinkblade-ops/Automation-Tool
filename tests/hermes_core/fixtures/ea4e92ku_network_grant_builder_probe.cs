using System;
using System.Collections.Generic;
using System.IO;

internal static class Ea4eNetworkGrantBuilderProbe
{
    private static readonly string[] Keys = {
        "grant_id", "nonce", "issuer_binary_sha256", "ceremony_id", "store_id",
        "store_epoch", "attempt_id", "authority_id", "request_hash",
        "predecessor_hash", "source_commit", "operator_sid",
        "docker_executable_sha256", "network_name", "issued_at", "expires_at",
    };
    private static readonly string[] LabelKeys = {
        "hermes.ea4e.attempt", "hermes.ea4e.candidate_sha256",
        "hermes.ea4e.profile", "hermes.ea4e.cleanup_owner",
    };

    private static int Main(string[] args)
    {
        if (args.Length != 1 + Keys.Length + LabelKeys.Length) return 2;
        try
        {
            var fields = new Dictionary<string, string>();
            var labels = new Dictionary<string, string>();
            for (int index = 0; index < Keys.Length; index++)
                fields.Add(Keys[index], args[index + 1]);
            for (int index = 0; index < LabelKeys.Length; index++)
                labels.Add(LabelKeys[index], args[index + 1 + Keys.Length]);
            byte[] artifact = Ea4eNetworkMutationGrantCandidate.BuildCompleteCandidate(
                fields, labels);
            File.WriteAllBytes(args[0], artifact);
            Console.WriteLine("BUILT:NON_AUTHORIZING_CANDIDATE");
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name);
            return 1;
        }
    }
}

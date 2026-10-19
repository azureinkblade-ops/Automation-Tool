using System;
using System.Collections.Generic;
using System.IO;

internal static class Ea4eProtectedGrantProbe
{
    private static readonly string[] Keys = {
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
        if (args.Length != 2 + Keys.Length + LabelKeys.Length) return 2;
        try
        {
            var expected = new Dictionary<string, string>();
            var labels = new Dictionary<string, string>();
            for (int index = 0; index < Keys.Length; index++)
                expected.Add(Keys[index], args[index + 2]);
            for (int index = 0; index < LabelKeys.Length; index++)
                labels.Add(LabelKeys[index], args[index + 2 + Keys.Length]);
            byte[] raw;
            if (args[0] == "build")
            {
                expected.Remove("artifact_hash");
                raw = Ea4eNetworkMutationGrantCandidate.BuildProtectedCandidate(
                    expected, labels);
                File.WriteAllBytes(args[1], raw);
                Console.WriteLine("BUILT:PURE_CONTRACT_ONLY");
                return 0;
            }
            else raw = File.ReadAllBytes(args[1]);
            if (args[0] == "fake")
                Ea4eNetworkMutationGrantCandidate.ReadCompleteIdentity(raw);
            else
            {
                if (!Ea4eNetworkMutationGrantCandidate.MatchesProtected(
                        raw, expected, labels)) return 1;
                Ea4eNetworkMutationGrantCandidate.ReadProtectedIdentity(raw);
            }
            Console.WriteLine("MATCH:PURE_CONTRACT_ONLY");
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name);
            return 1;
        }
    }
}

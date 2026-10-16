using System;
using System.Collections.Generic;
using System.IO;

internal static class Ea4eNetworkGrantV4StoreProbe
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
        if (args.Length < 3) return 2;
        try
        {
            if (args[0] == "init" && args.Length == 5)
            {
                using (Ea4eNetworkGrantV4Store.Initialize(
                    args[1], args[2], args[3], Int32.Parse(args[4]))) { }
            }
            else if (args[0] == "open" && args.Length == 3)
            {
                using (Ea4eNetworkGrantV4Store.Open(args[1], args[2])) { }
            }
            else if ((args[0] == "issue" || args[0] == "crash-issue"
                      || args[0] == "stale")
                     && args.Length == 4 + Keys.Length + LabelKeys.Length)
            {
                var expected = new Dictionary<string, string>();
                var labels = new Dictionary<string, string>();
                for (int index = 0; index < Keys.Length; index++)
                    expected.Add(Keys[index], args[index + 4]);
                for (int index = 0; index < LabelKeys.Length; index++)
                    labels.Add(LabelKeys[index], args[index + 4 + Keys.Length]);
                byte[] artifact = File.ReadAllBytes(args[3]);
                if (args[0] == "stale")
                {
                    using (var old = Ea4eNetworkGrantV4Store.Open(args[1], args[2]))
                    {
                        using (var current = Ea4eNetworkGrantV4Store.Open(args[1], args[2]))
                            current.IssueFake(artifact, expected, labels);
                        old.ClaimFake(expected["grant_id"], 1050);
                    }
                }
                else
                {
                    using (var store = Ea4eNetworkGrantV4Store.Open(args[1], args[2]))
                        store.IssueFake(artifact, expected, labels,
                                        args[0] == "crash-issue");
                }
            }
            else if (args.Length == 5)
            {
                using (var store = Ea4eNetworkGrantV4Store.Open(args[1], args[2]))
                {
                    long now = Int64.Parse(args[4]);
                    if (args[0] == "claim") store.ClaimFake(args[3], now);
                    else if (args[0] == "revoke") store.RevokeFake(args[3], now);
                    else if (args[0] == "uncertain") store.MarkUncertainFake(args[3], now);
                    else return 2;
                }
            }
            else return 2;
            Console.WriteLine("PASS:FAKE_ONLY");
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name + ":" + error.Message);
            return 1;
        }
    }
}

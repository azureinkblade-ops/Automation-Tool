using System;
using System.Collections.Generic;
using System.IO;

internal static class NetworkRequestProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 11)
            return 2;
        try
        {
            var file = new FileInfo(args[0]);
            if (file.Length < 1 || file.Length > 16384)
                return 1;
            byte[] raw = File.ReadAllBytes(file.FullName);
            var labels = new Dictionary<string, string> {
                { "hermes.ea4e.attempt", args[7] },
                { "hermes.ea4e.candidate_sha256", args[8] },
                { "hermes.ea4e.profile", args[9] },
                { "hermes.ea4e.cleanup_owner", args[10] },
            };
            bool match = Ea4eNetworkIssueRequestCandidate.Matches(
                raw, args[1], args[2], args[3], args[4], args[5], args[6], labels);
            Console.WriteLine(match ? "REQUEST_BYTES_MATCH_ONLY" : "DENY");
            return match ? 0 : 1;
        }
        catch (Exception)
        {
            Console.WriteLine("DENY");
            return 1;
        }
    }
}

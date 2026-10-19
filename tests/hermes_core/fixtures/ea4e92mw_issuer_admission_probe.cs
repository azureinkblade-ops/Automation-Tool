using System;
using System.IO;

internal static class Ea4eIssuerAdmissionProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 12) return 2;
        try
        {
            var policy = Ea4eProtectedIssuerPolicyCandidate.Read(
                File.ReadAllBytes(args[0]), args[1]);
            var token = new Ea4eProtectedIssuerToken.Observation(
                args[2], Boolean.Parse(args[3]));
            var image = new Ea4eProtectedIssuerImage.Observation(args[4], args[5]);
            string result = Ea4eProtectedIssuerAdmissionCandidate.Evaluate(
                policy, token, image, args[6], Int32.Parse(args[7]),
                args[8], args[9], Int64.Parse(args[10]), Int64.Parse(args[11]));
            Console.WriteLine(result);
            return result == "CANDIDATE_MATCH_NOT_AUTHORITY" ? 0 : 1;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name);
            return 1;
        }
    }
}

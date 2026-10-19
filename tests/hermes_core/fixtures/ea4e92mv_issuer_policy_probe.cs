using System;
using System.IO;

internal static class Ea4eIssuerPolicyProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 2) return 2;
        try
        {
            var policy = Ea4eProtectedIssuerPolicyCandidate.Read(
                File.ReadAllBytes(args[0]), args[1]);
            Console.WriteLine("MATCH:PURE_POLICY_BYTES:" + policy.Text("action")
                + ":" + policy.Number("store_epoch"));
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name);
            return 1;
        }
    }
}

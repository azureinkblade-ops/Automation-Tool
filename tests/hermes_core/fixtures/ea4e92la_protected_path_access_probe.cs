using System;
using System.Globalization;
using System.Security.Principal;

internal static class Ea4eProtectedPathAccessProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 3) return 2;
        if (args[0] == "MASK")
        {
            bool closure = args[1] == "CLOSURE";
            uint granted = UInt32.Parse(args[2], NumberStyles.HexNumber,
                                        CultureInfo.InvariantCulture);
            Console.WriteLine(Ea4eProtectedPathAccessCandidate
                .GrantsMutation(closure, granted) ? "BLOCK" : "ALLOW");
            return 0;
        }
        string sid = args[1] == "SELF"
            ? WindowsIdentity.GetCurrent().User.Value : args[1];
        string denial = Ea4eProtectedPathAccessCandidate
            .DenialForCurrentUnelevatedApp(args[0], args[2], sid);
        Console.WriteLine(denial == null ? "MATCH:ACL_SNAPSHOT_ONLY" : "DENY:" + denial);
        return denial == null ? 0 : 1;
    }
}

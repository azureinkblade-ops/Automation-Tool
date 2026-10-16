using System;
using System.Security.Principal;

internal static class Ea4eProtectedPathAccessProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 2) return 2;
        string sid = args[1] == "SELF"
            ? WindowsIdentity.GetCurrent().User.Value : args[1];
        string denial = Ea4eProtectedPathAccessCandidate
            .DenialForCurrentUnelevatedApp(args[0], sid);
        Console.WriteLine(denial == null ? "MATCH:ACL_SNAPSHOT_ONLY" : "DENY:" + denial);
        return denial == null ? 0 : 1;
    }
}

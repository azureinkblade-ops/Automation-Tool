using System;
using System.Security.Principal;

internal static class Ea4e92ldCombinedSnapshotProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 4) return 2;
        string sid = args[2] == "SELF"
            ? WindowsIdentity.GetCurrent().User.Value : args[2];
        string denial = Ea4eProtectedPathAccessCandidate
            .DenialWithByteSnapshotForCurrentUnelevatedApp(
                args[0], args[1], sid, args[3]);
        Console.WriteLine(denial == null
            ? "MATCH:ACL_AND_BYTE_SNAPSHOT_ONLY" : "DENY:" + denial);
        return denial == null ? 0 : 1;
    }
}

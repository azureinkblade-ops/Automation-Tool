using System;

internal static class Ea4e92lcProtectedByteSnapshotProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 2) return 2;
        string denial = Ea4eProtectedByteSnapshotCandidate.Denial(args[0], args[1]);
        Console.WriteLine(denial == null ? "MATCH:BYTE_SNAPSHOT_ONLY" : "DENY:" + denial);
        return denial == null ? 0 : 1;
    }
}

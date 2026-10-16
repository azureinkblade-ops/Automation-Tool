using System;

internal static class Ea4eProtectedPathTopologyProbe
{
    private static int Main(string[] args)
    {
        string denial = Ea4eProtectedPathTopologyCandidate.Denial(
            args.Length == 1 ? args[0] : null);
        Console.WriteLine(denial == null ? "MATCH:TOPOLOGY_ONLY" : "DENY:" + denial);
        return denial == null ? 0 : 1;
    }
}

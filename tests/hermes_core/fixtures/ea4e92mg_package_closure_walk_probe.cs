using System;
using System.Collections.Generic;

internal static class Ea4e92mgPackageClosureWalkProbe
{
    private static int Main(string[] args)
    {
        if (args.Length < 3 || args.Length % 2 != 1) return 2;
        var expected = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int index = 1; index < args.Length; index += 2)
        {
            if (expected.ContainsKey(args[index])) return 2;
            expected.Add(args[index], args[index + 1]);
        }
        string denial = Ea4ePackageClosureWalkCandidate.Denial(args[0], expected);
        Console.WriteLine(denial == null ? "MATCH:UNPROTECTED_WALK_ONLY" : "DENY:" + denial);
        return denial == null ? 0 : 1;
    }
}

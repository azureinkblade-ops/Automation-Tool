using System;

internal static class Ea4e92pcNamespacePathProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 2) return 2;
        string expected;
        string denial = Ea4eAnnouncementNamespacePathCandidate.Screen(
            args[0], args[1], out expected);
        Console.WriteLine(denial ?? "CANDIDATE:PATH_VALUES_ONLY:" + expected);
        return denial == null ? 0 : 1;
    }
}

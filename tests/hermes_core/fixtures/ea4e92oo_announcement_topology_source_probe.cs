using System;

internal static class Ea4e92ooAnnouncementTopologySourceProbe
{
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "share")
        {
            Console.WriteLine("{0:x8}",
                Ea4eProtectedPathTopologyCandidate.AnnouncementLeafShareMode());
            return 0;
        }
        if (args.Length == 2 && args[0] == "invalid-form")
        {
            Console.WriteLine(Ea4eProtectedPathTopologyCandidate
                .DenialWithAnnouncementLeaf(args[1],
                    (handle, path, isAncestor) => null));
            return 0;
        }
        if (args.Length == 1 && args[0] == "missing-observer")
        {
            Console.WriteLine(Ea4eProtectedPathTopologyCandidate
                .DenialWithAnnouncementLeaf("C:\\no-open", null));
            return 0;
        }
        return 2;
    }
}

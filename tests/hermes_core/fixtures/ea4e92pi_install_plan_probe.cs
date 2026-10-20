using System;

internal static class Ea4e92piInstallPlanProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 3) return 2;
        string[] paths;
        string sddl;
        string denial = Ea4eDirectoryInstallPlanCandidate.Build(
            args[0], args[1], args[2], out paths, out sddl);
        if (denial != null)
        {
            Console.WriteLine(denial);
            return 1;
        }
        Console.WriteLine("CANDIDATE:PLAN_VALUES_ONLY");
        Console.WriteLine(Ea4eDirectoryInstallPlanCandidate.DisallowPathRedirects);
        Console.WriteLine(Ea4eDirectoryInstallPlanCandidate.ShareReadWriteNoDelete);
        Console.WriteLine(Ea4eDirectoryInstallPlanCandidate.DirectoryReadbackAccess.ToString("x8"));
        foreach (string path in paths) Console.WriteLine(path);
        Console.WriteLine(sddl);
        return 0;
    }
}

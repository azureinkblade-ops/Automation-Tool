using System;

internal static class Ea4e92pfDirectory2ExportProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1 || args[0] != "--export") return 2;
        string result = Ea4eDirectory2AvailabilityCandidate.Observe();
        Console.WriteLine(result);
        return result == "CANDIDATE:EXPORT_PRESENT_ONLY" ? 0 : 1;
    }
}

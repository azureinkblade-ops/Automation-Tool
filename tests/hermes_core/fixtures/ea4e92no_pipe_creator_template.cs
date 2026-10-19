using System;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        try
        {
            Console.WriteLine(Ea4eProtectedPipeCreatorCandidate.BuildSddl(args[0]));
            return 0;
        }
        catch (InvalidOperationException)
        {
            Console.WriteLine("DENY:APP_SID_OR_DESCRIPTOR");
            return 0;
        }
    }
}

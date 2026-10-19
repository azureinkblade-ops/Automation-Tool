using System;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "MODE")
        {
            Console.WriteLine(Ea4eProtectedPipeCreatorCandidate.ProposedOpenMode().ToString("X8"));
            return 0;
        }
        if (args.Length == 3 && args[0] == "NAME")
        {
            try
            {
                Console.WriteLine(Ea4eProtectedPipeCreatorCandidate.BuildPipeName(
                    Guid.Parse(args[1]), Guid.Parse(args[2])));
            }
            catch (FormatException)
            {
                Console.WriteLine("DENY:PIPE_NAME");
            }
            catch (InvalidOperationException)
            {
                Console.WriteLine("DENY:PIPE_NAME");
            }
            return 0;
        }
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

using System;
using System.Security.AccessControl;

internal static class Ea4e92NtPipeReadbackScreenProbe
{
    private static int Main(string[] args)
    {
        if (args.Length < 2 || args.Length > 3) return 2;
        try
        {
            byte[] bytes;
            if (args[0] == "short") bytes = new byte[8];
            else if (args[0] == "invalid") bytes = new byte[30];
            else
            {
                string sddl = args[0] == "template"
                    ? Ea4eProtectedPipeCreatorCandidate.BuildSddl(args[1])
                    : args[2];
                var descriptor = new RawSecurityDescriptor(sddl);
                bytes = new byte[descriptor.BinaryLength];
                descriptor.GetBinaryForm(bytes, 0);
            }
            Console.WriteLine(Ea4eProtectedPipeReadbackCandidate.ScreenBytes(
                bytes, args[1]));
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:PROBE:" + error.GetType().Name);
            return 1;
        }
    }
}

using System;
using System.Globalization;

internal static class Ea4e92ogPipeAccessPolicyProbe
{
    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "mask")
        {
            try
            {
                Console.WriteLine(Ea4eProtectedPipeAccessProbePolicy
                    .RequestedAccess(args[1]).ToString("x8"));
                return 0;
            }
            catch (ArgumentException)
            {
                Console.WriteLine("DENY:UNKNOWN_ATTEMPT");
                return 1;
            }
        }
        int error;
        if (args.Length == 4 && args[0] == "classify" &&
            (args[2] == "0" || args[2] == "1") &&
            Int32.TryParse(args[3], NumberStyles.None,
                CultureInfo.InvariantCulture, out error))
        {
            Console.WriteLine(Ea4eProtectedPipeAccessProbePolicy.Classify(
                args[1], args[2] == "1", error));
            return 0;
        }
        return 2;
    }
}

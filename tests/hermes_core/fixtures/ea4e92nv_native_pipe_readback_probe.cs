// Source-only fixture. The native mode requires a separately bounded ceremony.
using System;
using System.Globalization;

internal static class Ea4e92nvNativePipeReadbackProbe
{
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--describe")
        {
            Console.WriteLine("SOURCE_ONLY:ONE_PIPE_READBACK_NO_CLIENT");
            return 0;
        }
        if (args.Length != 5 || args[0] != "--native-readback")
            return 2;

        Guid ceremony;
        DateTime deadline;
        if (!Guid.TryParseExact(args[3], "D", out ceremony) ||
            ceremony == Guid.Empty ||
            !DateTime.TryParseExact(args[4], "yyyy-MM-ddTHH:mm:ssZ",
                CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal |
                DateTimeStyles.AdjustToUniversal, out deadline))
            return Deny("INPUT");
        TimeSpan remaining = deadline - DateTime.UtcNow;
        if (remaining <= TimeSpan.Zero || remaining > TimeSpan.FromMinutes(2))
            return Deny("DEADLINE");

        try
        {
            var token = Ea4eProtectedIssuerToken.ReadCurrent();
            if (Ea4eProtectedIssuerToken.Evaluate(args[2], token)
                != "MATCH_ELEVATED_TOKEN")
                return Deny("OPERATOR_TOKEN");
            string name;
            using (var pipe = Ea4eProtectedPipeCreatorCandidate.Open(
                args[1], ceremony, out name))
            {
                string readback = Ea4eProtectedPipeReadbackCandidate.Read(
                    pipe, args[1]);
                if (readback != "CANDIDATE:READBACK_STRUCTURE_ONLY")
                    return Deny("READBACK");
                Console.WriteLine("CANDIDATE:READBACK_ONLY:" + name);
                return 0;
            }
        }
        catch (Exception error)
        {
            if (error is OutOfMemoryException || error is StackOverflowException)
                throw;
            return Deny("NATIVE_ERROR");
        }
    }

    private static int Deny(string reason)
    {
        Console.WriteLine("DENY:" + reason);
        return 1;
    }
}

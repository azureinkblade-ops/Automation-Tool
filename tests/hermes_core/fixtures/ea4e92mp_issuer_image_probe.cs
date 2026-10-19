using System;

internal static class Ea4eIssuerImageProbe
{
    private static int Main(string[] args)
    {
        try
        {
            string result;
            if (args.Length == 3 && args[0] == "current")
                result = Ea4eProtectedIssuerImage.Evaluate(
                    args[1], args[2], Ea4eProtectedIssuerImage.ReadCurrent());
            else if (args.Length == 5 && args[0] == "fake")
                result = Ea4eProtectedIssuerImage.Evaluate(
                    args[1], args[2],
                    new Ea4eProtectedIssuerImage.Observation(args[3], args[4]));
            else return 2;
            Console.WriteLine(result);
            return result == "MATCH_IMAGE_BYTES" ? 0 : 1;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name);
            return 1;
        }
    }
}

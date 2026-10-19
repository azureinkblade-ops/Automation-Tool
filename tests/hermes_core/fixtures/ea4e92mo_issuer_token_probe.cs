using System;

internal static class Ea4eIssuerTokenProbe
{
    private static int Main(string[] args)
    {
        try
        {
            string result;
            if (args.Length == 2 && args[0] == "current")
                result = Ea4eProtectedIssuerToken.Evaluate(
                    args[1], Ea4eProtectedIssuerToken.ReadCurrent());
            else if (args.Length == 4 && args[0] == "fake")
                result = Ea4eProtectedIssuerToken.Evaluate(
                    args[1], new Ea4eProtectedIssuerToken.Observation(
                        args[2], args[3] == "true"));
            else return 2;
            Console.WriteLine(result);
            return result == "MATCH_ELEVATED_TOKEN" ? 0 : 1;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name);
            return 1;
        }
    }
}

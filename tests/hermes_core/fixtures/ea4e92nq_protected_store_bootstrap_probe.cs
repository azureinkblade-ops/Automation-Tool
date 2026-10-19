using System;

internal static class Ea4e92NqProtectedStoreBootstrapProbe
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 5 && args[0] == "init")
            {
                using (Ea4eProtectedNetworkGrantStoreBootstrap.Initialize(
                    args[1], args[2], args[3], Int32.Parse(args[4]))) { }
                return 0;
            }
            if (args.Length == 3 && args[0] == "open")
            {
                using (Ea4eProtectedNetworkGrantStoreBootstrap.Open(
                    args[1], args[2])) { }
                return 0;
            }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.GetType().Name);
            return 1;
        }
        return 2;
    }
}

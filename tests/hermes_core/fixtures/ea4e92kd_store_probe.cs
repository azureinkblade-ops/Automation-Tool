using System;

internal static class StoreProbe
{
    private static int Main(string[] args)
    {
        if (args.Length < 3)
            return 2;
        try
        {
            if (args[0] == "init" && args.Length == 5)
            {
                using (Ea4eDockerMutationStoreIdentity.Initialize(
                    args[1], args[2], args[3], Int32.Parse(args[4]))) { }
            }
            else if (args[0] == "open" && args.Length == 3)
            {
                using (Ea4eDockerMutationStoreIdentity.Open(args[1], args[2])) { }
            }
            else if (args[0] == "advance" && args.Length == 4)
            {
                using (var store = Ea4eDockerMutationStoreIdentity.Open(args[1], args[2]))
                    store.RecordFakeEvent(args[3]);
            }
            else if (args[0] == "stale" && args.Length == 4)
            {
                using (var first = Ea4eDockerMutationStoreIdentity.Open(args[1], args[2]))
                using (var second = Ea4eDockerMutationStoreIdentity.Open(args[1], args[2]))
                {
                    first.RecordFakeEvent(args[3]);
                    second.RecordFakeEvent(args[3]);
                }
                return 3;
            }
            else
            {
                return 2;
            }
            Console.WriteLine("STORE_IDENTITY_PASS");
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name + ":" + error.Message);
            return 1;
        }
    }
}

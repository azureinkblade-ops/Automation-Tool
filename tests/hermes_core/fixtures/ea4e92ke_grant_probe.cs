using System;

internal static class FakeGrantProbe
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
            else if (args[0] == "issue" && args.Length == 13)
            {
                using (var store = Ea4eDockerMutationStoreIdentity.Open(args[1], args[2]))
                    new Ea4eFakeDockerMutationGrants(store).IssueFake(
                        args[3], args[4], args[5], args[6], args[7], args[8],
                        args[9], args[10], Int64.Parse(args[11]), Int64.Parse(args[12]));
            }
            else if (args[0] == "claim" && args.Length == 9)
            {
                using (var store = Ea4eDockerMutationStoreIdentity.Open(args[1], args[2]))
                    new Ea4eFakeDockerMutationGrants(store).ClaimFake(
                        args[3], args[4], args[5], args[6], args[7],
                        Int64.Parse(args[8]));
            }
            else if (args[0] == "revoke" && args.Length == 4)
            {
                using (var store = Ea4eDockerMutationStoreIdentity.Open(args[1], args[2]))
                    new Ea4eFakeDockerMutationGrants(store).RevokeFake(args[3]);
            }
            else
            {
                return 2;
            }
            Console.WriteLine("FAKE_GRANT_PASS");
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("DENY:" + error.GetType().Name + ":" + error.Message);
            return 1;
        }
    }
}

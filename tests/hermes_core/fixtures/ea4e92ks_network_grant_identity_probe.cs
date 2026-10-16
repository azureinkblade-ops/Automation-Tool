using System;
using System.IO;

internal static class Ea4eNetworkGrantIdentityProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        try
        {
            var identity = Ea4eNetworkMutationGrantCandidate.ReadCompleteIdentity(
                File.ReadAllBytes(args[0]));
            Console.WriteLine(String.Join("|", new[] {
                identity.GrantId, identity.Nonce, identity.AttemptId,
                identity.Action, identity.NetworkName,
            }));
            return 0;
        }
        catch (InvalidOperationException)
        {
            Console.WriteLine("DENY");
            return 1;
        }
    }
}

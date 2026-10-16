using System;
using System.IO;

internal static class Ea4eV4DigestProbe
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 4 && args[0] == "row")
            {
                var row = new Ea4eNetworkGrantV4Digest.Row(
                    args[1], File.ReadAllBytes(args[2]), args[3]);
                Console.WriteLine(Ea4eNetworkGrantV4Digest.RowHash(row));
                return 0;
            }
            if (args.Length == 4 && args[0] == "snapshot")
            {
                byte[] bytes = File.ReadAllBytes(args[2]);
                var row = new Ea4eNetworkGrantV4Digest.Row(args[1], bytes, args[3]);
                string before = Ea4eNetworkGrantV4Digest.RowHash(row);
                bytes[0] ^= 1;
                Console.WriteLine(before == Ea4eNetworkGrantV4Digest.RowHash(row)
                    ? "SNAPSHOT_OK" : "DENY");
                return before == Ea4eNetworkGrantV4Digest.RowHash(row) ? 0 : 1;
            }
            if (args.Length == 7 && args[0] == "table")
            {
                var first = new Ea4eNetworkGrantV4Digest.Row(
                    args[1], File.ReadAllBytes(args[2]), args[3]);
                var second = new Ea4eNetworkGrantV4Digest.Row(
                    args[4], File.ReadAllBytes(args[5]), args[6]);
                Console.WriteLine(Ea4eNetworkGrantV4Digest.TableHash(
                    new[] { first, second }));
                return 0;
            }
        }
        catch (Exception)
        {
            Console.WriteLine("DENY");
            return 1;
        }
        return 2;
    }
}

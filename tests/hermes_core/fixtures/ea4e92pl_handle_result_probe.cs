using System;

internal static class Ea4e92plHandleResultProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        long value;
        if (!long.TryParse(args[0], out value)) return 2;
        try
        {
            Console.WriteLine(Ea4eDirectory2HandleResultCandidate.Screen(
                new IntPtr(value)));
            return 0;
        }
        catch (OverflowException)
        {
            return 2;
        }
    }
}

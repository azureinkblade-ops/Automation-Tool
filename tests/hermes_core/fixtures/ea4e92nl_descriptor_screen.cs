using System;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length != 2)
            return 2;
        Console.WriteLine(Ea4eProtectedPipeDescriptorScreen.Screen(args[0], args[1]));
        return 0;
    }
}

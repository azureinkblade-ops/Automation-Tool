using System;
using System.IO.Pipes;

internal static class Ea4e92lnPipeIntegrityLabelProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        if (args[0] == "INVALID")
        {
            Console.WriteLine(Ea4ePipeIntegrityLabelCandidate.Observe(null));
            return 0;
        }
        if (args[0] != "FIXTURE") return 2;
        string name = "ea4e92ln-" + Guid.NewGuid().ToString("N");
        using (var pipe = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Byte))
        {
            Console.WriteLine(Ea4ePipeIntegrityLabelCandidate.Observe(
                pipe.SafePipeHandle));
        }
        return 0;
    }
}

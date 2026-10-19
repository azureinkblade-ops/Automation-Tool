using System;
using System.Diagnostics;
using System.IO.Pipes;
using System.Security.Principal;
using System.Threading;
using System.Threading.Tasks;

internal static class Ea4e92mzPipeClientPathProbe
{
    private static int Main(string[] args)
    {
        if (args.Length < 3 || args.Length > 4) return 2;
        string mode = args[0];
        string expectedSid = mode == "WRONG_SID" ? "S-1-5-18"
            : WindowsIdentity.GetCurrent().User.Value;
        string expectedHash = mode == "BAD_HASH" ? "not-a-hash" : null;
        string name = "ea4e92mz-" + Guid.NewGuid().ToString("N");
        using (var server = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Byte))
        using (var release = new ManualResetEventSlim(false))
        using (var current = Process.GetCurrentProcess())
        using (var other = mode == "WRONG_PROCESS"
            ? Process.GetProcessById(int.Parse(args[3])) : null)
        {
            Task client = Task.Run(() =>
            {
                using (var connection = new NamedPipeClientStream(
                    ".", name, PipeDirection.Out))
                {
                    connection.Connect(3000);
                    connection.WriteByte(0x4d);
                    connection.Flush();
                    release.Wait(3000);
                }
            });
            Task accept = Task.Run(() => server.WaitForConnection());
            if (!accept.Wait(5000))
            {
                release.Set();
                Console.WriteLine("DENY:PIPE_CONNECTION_UNAVAILABLE");
                return 1;
            }
            if (server.ReadByte() != 0x4d) return 3;
            string denial;
            try
            {
                denial = Ea4ePipeClientPathObservationCandidate.Denial(
                    server.SafePipeHandle,
                    other == null ? current.Handle : other.Handle,
                    expectedSid, args[1], args[2], expectedHash);
            }
            finally
            {
                release.Set();
                client.Wait(3000);
            }
            Console.WriteLine(denial == null
                ? "MATCH:OBSERVATION_ONLY" : "DENY:" + denial);
            return denial == null ? 0 : 1;
        }
    }
}

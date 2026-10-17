using System;
using System.Diagnostics;
using System.IO.Pipes;
using System.Security.Principal;
using System.Threading;
using System.Threading.Tasks;

internal static class Ea4e92ljPipeClientBindingProbe
{
    private static int Main(string[] args)
    {
        if (args.Length < 1 || args.Length > 2) return 2;
        string expectedSid = args[0] == "WRONG_SID" ? "S-1-5-18"
            : args[0] == "BAD_SID" ? "not-a-sid"
            : WindowsIdentity.GetCurrent().User.Value;
        string name = "ea4e92lj-" + Guid.NewGuid().ToString("N");
        using (var server = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Byte))
        using (var release = new ManualResetEventSlim(false))
        using (var current = Process.GetCurrentProcess())
        using (var other = args[0] == "WRONG_PROCESS"
            ? Process.GetProcessById(int.Parse(args[1])) : null)
        {
            Task client = Task.Run(() =>
            {
                using (var connection = new NamedPipeClientStream(
                    ".", name, PipeDirection.Out))
                {
                    connection.Connect(3000);
                    connection.WriteByte(0x4a);
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
            if (server.ReadByte() != 0x4a) return 3;
            string denial;
            try
            {
                denial = Ea4ePipeClientBindingCandidate.Denial(
                    server.SafePipeHandle,
                    other == null ? current.Handle : other.Handle,
                    expectedSid);
            }
            finally
            {
                release.Set();
                client.Wait(3000);
            }
            Console.WriteLine(denial == null
                ? "MATCH:PIPE_CLIENT_OBSERVED_ONLY" : "DENY:" + denial);
            return denial == null ? 0 : 1;
        }
    }
}

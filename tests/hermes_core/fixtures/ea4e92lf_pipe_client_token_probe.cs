using System;
using System.IO.Pipes;
using System.Security.Principal;
using System.Threading;
using System.Threading.Tasks;

internal static class Ea4e92lfPipeClientTokenProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        string expectedSid = args[0] == "SELF"
            ? WindowsIdentity.GetCurrent().User.Value : args[0];
        string name = "ea4e92lf-" + Guid.NewGuid().ToString("N");
        using (var server = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Byte))
        using (var release = new ManualResetEventSlim(false))
        {
            Task client = Task.Run(() =>
            {
                using (var connection = new NamedPipeClientStream(".", name, PipeDirection.Out))
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
                Console.WriteLine(client.IsFaulted
                    ? "DENY:PIPE_CONNECTION_FAILED" : "DENY:PIPE_CONNECTION_TIMEOUT");
                release.Set();
                return 1;
            }
            if (client.IsFaulted)
            {
                Console.WriteLine("DENY:PIPE_CONNECTION_FAILED");
                release.Set();
                return 1;
            }
            if (server.ReadByte() != 0x4a) return 3;
            string denial;
            try
            {
                denial = Ea4ePipeClientTokenCandidate.Denial(
                    server.SafePipeHandle, expectedSid);
            }
            finally
            {
                release.Set();
                client.Wait(3000);
            }
            Console.WriteLine(denial == null
                ? "MATCH:CLIENT_TOKEN_OBSERVED_ONLY" : "DENY:" + denial);
            return denial == null ? 0 : 1;
        }
    }
}

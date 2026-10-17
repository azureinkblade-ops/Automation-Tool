using System;
using System.Diagnostics;
using System.IO.Pipes;
using System.Threading;
using System.Threading.Tasks;

internal static class Ea4e92lgPipeClientProcessProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        string name = "ea4e92lg-" + Guid.NewGuid().ToString("N");
        using (var server = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Byte))
        using (var release = new ManualResetEventSlim(false))
        using (var current = Process.GetCurrentProcess())
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
            IntPtr expected;
            switch (args[0])
            {
                case "CURRENT": expected = current.Handle; break;
                case "NULL": expected = IntPtr.Zero; break;
                case "PSEUDO": expected = new IntPtr(-1); break;
                case "THREAD": expected = new IntPtr(-2); break;
                default: throw new ArgumentException("invalid mode");
            }
            string denial;
            try
            {
                denial = Ea4ePipeClientProcessCandidate.Denial(
                    server.SafePipeHandle, expected);
            }
            finally
            {
                release.Set();
                client.Wait(3000);
            }
            Console.WriteLine(denial == null
                ? "MATCH:PROCESS_OBJECT_OBSERVED_ONLY" : "DENY:" + denial);
            return denial == null ? 0 : 1;
        }
    }
}

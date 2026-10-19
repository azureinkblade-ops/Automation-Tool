using System;
using System.Diagnostics;
using System.IO.Pipes;
using System.Threading;
using System.Threading.Tasks;

internal static class Ea4e92naPipeProcessLeaseProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        if (args[0] == "NO_PIPE")
        {
            Console.WriteLine("DENY:" +
                Ea4ePipeClientProcessLeaseCandidate.Denial(null, null));
            return 1;
        }
        string name = "ea4e92na-" + Guid.NewGuid().ToString("N");
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
                    connection.WriteByte(0x4e);
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
            if (server.ReadByte() != 0x4e) return 3;
            int callbacks = 0;
            string denial;
            try
            {
                Func<IntPtr, uint, long, string> observer =
                    (handle, pid, creation) =>
                    {
                        callbacks++;
                        if (handle == IntPtr.Zero || pid != (uint)current.Id
                            || creation <= 0)
                            return "PROCESS_OBSERVATION_MISMATCH";
                        return args[0] == "CALLBACK_DENY"
                            ? "CALLBACK_DENIED" : null;
                    };
                denial = Ea4ePipeClientProcessLeaseCandidate.Denial(
                    server.SafePipeHandle,
                    args[0] == "NO_OBSERVER" ? null : observer);
            }
            finally
            {
                release.Set();
                client.Wait(3000);
            }
            if (args[0] != "NO_OBSERVER" && callbacks != 1)
                denial = "CALLBACK_COUNT_MISMATCH";
            Console.WriteLine(denial == null
                ? "MATCH:KERNEL_CLIENT_PROCESS_OBSERVED_ONLY"
                : "DENY:" + denial);
            return denial == null ? 0 : 1;
        }
    }
}

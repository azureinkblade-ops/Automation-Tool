using System;
using System.IO.Pipes;
using System.Threading;
using System.Threading.Tasks;

internal static class Ea4e92ngPipeMessageProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        string mode = args[0];
        string name = "ea4e92ng-" + Guid.NewGuid().ToString("N");
        using (var server = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Message,
            PipeOptions.Asynchronous))
        using (var release = new ManualResetEventSlim(false))
        {
            Task client = Task.Run(() =>
            {
                using (var connection = new NamedPipeClientStream(
                    ".", name, PipeDirection.Out))
                {
                    connection.Connect(3000);
                    if (mode == "VALID") connection.Write(new byte[] { 1, 2, 3 }, 0, 3);
                    if (mode == "OVERSIZE") connection.Write(new byte[513], 0, 513);
                    if (mode == "TIMEOUT") release.Wait(3000);
                }
            });
            try
            {
                Task accept = server.WaitForConnectionAsync();
                if (!accept.Wait(3000)) return 3;
                byte[] frame;
                string denial = Ea4ePipeChallengeMessageCandidate.Capture(
                    server, 200, out frame);
                string result = denial ?? (frame.Length == 3 && frame[0] == 1
                    ? "BYTES_ONLY" : "WRONG_BYTES");
                Console.WriteLine(result);
                return 0;
            }
            finally
            {
                release.Set();
                try { client.Wait(3000); }
                catch (AggregateException) { }
            }
        }
    }
}

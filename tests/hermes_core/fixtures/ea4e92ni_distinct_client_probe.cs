using System;
using System.Diagnostics;
using System.IO.Pipes;
using System.Threading.Tasks;

internal static class Ea4e92niDistinctClientProbe
{
    private static int Main(string[] args)
    {
        if ((args.Length == 2 || args.Length == 3) && args[0] == "CLIENT")
        {
            using (var connection = new NamedPipeClientStream(
                ".", args[1], PipeDirection.Out))
            {
                connection.Connect(3000);
                byte[] message = args.Length == 3
                    ? Convert.FromBase64String(args[2]) : new byte[] { 1, 2, 3 };
                connection.Write(message, 0, message.Length);
                Console.ReadLine();
                return 0;
            }
        }
        bool wire = args.Length == 2 && args[0] == "WIRE";
        if (!wire && (args.Length != 1 ||
            (args[0] != "MATCH" && args[0] != "PID_MISMATCH" &&
             args[0] != "CREATION_MISMATCH"))) return 2;

        string name = "ea4e92ni-" + Guid.NewGuid().ToString("N");
        using (var server = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Message,
            PipeOptions.Asynchronous))
        using (var current = Process.GetCurrentProcess())
        {
            var start = new ProcessStartInfo(current.MainModule.FileName,
                "CLIENT " + name + (wire ? " " + args[1] : ""))
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using (Process child = Process.Start(start))
            {
                if (child == null) return 3;
                try
                {
                    Task accept = server.WaitForConnectionAsync();
                    if (!accept.Wait(3000)) return 4;
                    uint expected = (uint)child.Id;
                    long expectedCreation = child.StartTime.ToFileTimeUtc();
                    if (args[0] == "PID_MISMATCH") expected++;
                    if (args[0] == "CREATION_MISMATCH") expectedCreation++;
                    byte[] frame;
                    string denial = Ea4ePipeChallengeMessageCandidate.CaptureAndObserve(
                        server, 1000,
                        handle => Ea4ePipeClientProcessLeaseCandidate.Denial(
                            handle, (process, pid, creation) =>
                                pid == expected && creation == expectedCreation
                                    ? null : "CLIENT_IDENTITY_MISMATCH"),
                        out frame);
                    string result = denial ?? (wire
                        ? "WIRE_BASE64:" + Convert.ToBase64String(frame)
                        : frame.Length == 3 && frame[0] == 1
                            ? "DISTINCT_CLIENT_OBSERVED_ONLY" : "WRONG_BYTES");
                    Console.WriteLine(result);
                    return 0;
                }
                finally
                {
                    child.StandardInput.WriteLine();
                    if (!child.WaitForExit(3000))
                    {
                        child.Kill();
                        child.WaitForExit(3000);
                    }
                }
            }
        }
    }
}

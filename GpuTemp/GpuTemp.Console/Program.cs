using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Timers;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace GpuTemp.CLI
{
    public class Program
    {
        private static Settings _conf = null;

        public static async Task Main(string[] args)
        {
            using (var file = File.OpenText("./appsettings.json"))
            using (var reader = new JsonTextReader(file))
            {
                _conf = JToken.ReadFrom(reader).ToObject<Settings>();
            }

            if (_conf == null)
            {
                Console.WriteLine("Failed to read config");
                return;
            }

            var timer = new Timer(_conf.PollingSeconds * 1000);

            timer.Elapsed += (s, a) => Task.Run(Poll);
            
            timer.Start();

            while (Console.ReadLine() != "exit")
            {
                
            }
        }

        private static async Task Poll()
        {
            var procInfo = new ProcessStartInfo()
            {
                RedirectStandardError = true,
                RedirectStandardOutput = true,
                Arguments = _conf.NVidiaSmi
            };

            if (OperatingSystem.IsWindows())
            {
                procInfo.FileName = "cmd";
                procInfo.Arguments = $"/c \"{_conf.NVidiaSmi}\"";
            }
            else
            {
                procInfo.FileName = "bash";
                procInfo.Arguments = $"-c \"{_conf.NVidiaSmi}\"";
            }

            string stdout;

            using (var proc = new Process())
            {
                proc.StartInfo = procInfo;
                proc.Start();
                proc.WaitForExit();

                if (proc.ExitCode != 0)
                {
                    Console.WriteLine($"{nameof(Settings.NVidiaSmi)} failed with error\n{proc.StandardError.ReadToEnd()}");
                    return;
                }

                stdout = proc.StandardOutput.ReadToEnd();
            }

            var tempRx = new Regex(_conf.TempRx, RegexOptions.Multiline | RegexOptions.IgnoreCase | RegexOptions.ExplicitCapture);
            var m = tempRx.Match(stdout);

            if (m.Success && m.Groups["temp"]?.Value is string temp)
            {
                Console.WriteLine($"GPU Temp:\t{temp}");
                return;
            }

            Console.WriteLine("Didn't find temp match");
        }
    }

    public class Settings
    {
        [JsonProperty("nvsmi")] public string NVidiaSmi { get; set; }

        public string TempRx { get; set; }

        public int PollingSeconds { get; set; }
    }
}
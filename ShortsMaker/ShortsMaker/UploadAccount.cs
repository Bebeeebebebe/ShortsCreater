using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading.Tasks;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;
namespace ShortsMaker
{
    public class UploadAccountStyle : INotifyPropertyChanged
    {
        private UploadPlatform platform;
        private string name;
        private string cookiesPath;

        public ObservableCollection<UploadPlatform> Platforms { get; }
            = new ObservableCollection<UploadPlatform>(
                Enum.GetValues(typeof(UploadPlatform)).Cast<UploadPlatform>());

        public UploadPlatform Platform
        {
            get => platform;
            set { platform = value; OnPropertyChanged(); }
        }

        public string Name
        {
            get => name;
            set { name = value; OnPropertyChanged(); }
        }

        public string CookiesPath
        {
            get => cookiesPath;
            set { cookiesPath = value; OnPropertyChanged(); }
        }

        // заглушка под авторизацию
        public async Task AuthorizeAsync()
        {
            if (string.IsNullOrWhiteSpace(Name))
                throw new InvalidOperationException("Account name is empty");

            var request = new LoginAccountRequest
            {
                account_name = Name,
                platform = Platform.ToString()
            };

            using var client = new HttpClient();

            client.BaseAddress = new Uri("http://localhost:8000"); // твой API

            var response = await client.PostAsJsonAsync("/LoginAccount/", request);

            if (!response.IsSuccessStatusCode)
            {
                var error = await response.Content.ReadAsStringAsync();
                throw new Exception($"API Error: {error}");
            }
        }

        public event PropertyChangedEventHandler PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string name = null)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }

    public class LoginAccountRequest
    {
        public string account_name { get; set; }
        public string platform { get; set; }
    }


}

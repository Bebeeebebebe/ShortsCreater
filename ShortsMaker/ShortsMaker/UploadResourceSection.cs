using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading.Tasks;

namespace ShortsMaker
{
    public enum UploadPlatform
    {
        YouTube,
        TikTok,
        ChatGPT
    }

    public class UploadResourceStyle : EditableSection
    {
        private UploadPlatform platform;
        private string videoType;
        private string description;
        private string hashtags;
        private string soundAuthor;
        private string soundTitle;


        // список аккаунтов для отображения
        public ObservableCollection<UploadAccountInResource> Accounts { get; }
    = new ObservableCollection<UploadAccountInResource>();

        public ObservableCollection<UploadPlatform> Platforms { get; }
            = new ObservableCollection<UploadPlatform>(
                Enum.GetValues(typeof(UploadPlatform)).Cast<UploadPlatform>());

        public ObservableCollection<string> VideoTypes { get; }
            = new ObservableCollection<string>();

        public UploadPlatform Platform
        {
            get => platform;
            set
            {
                platform = value;
                OnPropertyChanged();
                UpdateVideoTypes();
                ParseAccounts(); // 🔹 хук под будущую логику
            }
        }

        private string GetAccountsRootPath()
        {
            var baseDir = AppDomain.CurrentDomain.BaseDirectory;

            // 1️⃣ если Accounts лежит рядом с exe (production)
            var localAccounts = Path.Combine(baseDir, "Accounts");
            if (Directory.Exists(localAccounts))
                return localAccounts;

            // 2️⃣ если запуск из VS (поднимаемся вверх)
            var dir = new DirectoryInfo(baseDir);
            while (dir != null)
            {
                var testPath = Path.Combine(dir.FullName, "Accounts");
                if (Directory.Exists(testPath))
                    return testPath;

                dir = dir.Parent;
            }

            throw new DirectoryNotFoundException("Accounts folder not found.");
        }
        public string VideoType
        {
            get => videoType;
            set { videoType = value; OnPropertyChanged(); }
        }

        public string Description
        {
            get => description;
            set { description = value; OnPropertyChanged(); }
        }

        public string Hashtags
        {
            get => hashtags;
            set { hashtags = value; OnPropertyChanged(); }
        }


        public string SoundAuthor
        {
            get => soundAuthor;
            set { soundAuthor = value; OnPropertyChanged(); }
        }

        public string SoundTitle
        {
            get => soundTitle;
            set { soundTitle = value; OnPropertyChanged(); }
        }
        private void ParseAccounts()
        {
            Accounts.Clear();

            if (Platform == default)
                return;

            var accountsRoot = GetAccountsRootPath();
            var platformFolder = Platform.ToString().ToLower();
            var platformPath = Path.Combine(accountsRoot, platformFolder);

            if (!Directory.Exists(platformPath))
                return;

            var files = Directory.GetFiles(platformPath, "*.pkl");

            foreach (var file in files)
            {
                Accounts.Add(new UploadAccountInResource
                {
                    CookiesPath = file,
                    Platform = Platform,
                    IsSelected = false
                });
            }
        }
        private void UpdateVideoTypes()
        {
            VideoTypes.Clear();
            VideoType = null;

            switch (Platform)
            {
                case UploadPlatform.YouTube:
                    VideoTypes.Add("Shorts");
                    VideoTypes.Add("Обычное видео");
                    break;

                case UploadPlatform.TikTok:
                    VideoTypes.Add("TikTok видео");
                    break;
            }
        }

        public event PropertyChangedEventHandler PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string name = null)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

        public UploadResourceStyle()
        {
            Platform = UploadPlatform.TikTok;
        }
    }



    public class UploadResourceSection : EditableSection
    {
        public UploadResourceStyle Style { get; } = new UploadResourceStyle();

        public UploadResourceSection()
        {
            SectionType = SectionType.Upload;
            Title = "Ресурс выгрузки";
            Description = "Параметры публикации видео";
            IsEnabled = true;
        }
    }
    public class VideoSideTextsDto
    {
        public string description { get; set; }
        public string hashtags { get; set; }
        public string music_author { get; set; }
        public string music_name { get; set; }
    }
    public class MultiPostSingleRequestDto
    {
        public string platform { get; set; }
        public string account_name { get; set; }

        public Dictionary<string, VideoSideTextsDto> videos { get; set; }
    }
    public class MultiPostRequestDto
    {
        public List<MultiPostSingleRequestDto> requests { get; set; }
    }
}

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading.Tasks;
using System.IO;


namespace ShortsMaker
{
    public class UploadAccountInResource : INotifyPropertyChanged
    {
        private bool isSelected;
        private string cookiesPath;
        private UploadPlatform platform;

        public bool IsSelected
        {
            get => isSelected;
            set { isSelected = value; OnPropertyChanged(); }
        }

        public string CookiesPath
        {
            get => cookiesPath;
            set { cookiesPath = value; OnPropertyChanged(); }
        }

        public UploadPlatform Platform
        {
            get => platform;
            set { platform = value; OnPropertyChanged(); }
        }

        public string DisplayName => Path.GetFileNameWithoutExtension(CookiesPath);

        public event PropertyChangedEventHandler PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string name = null)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }
}

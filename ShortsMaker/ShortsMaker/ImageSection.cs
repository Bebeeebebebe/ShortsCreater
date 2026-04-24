using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading.Tasks;
using static ShortsMaker.SubtitleStyle;
using System.Windows.Forms;
using System.Windows.Input;
using System.Collections.ObjectModel;



namespace ShortsMaker
{
    public enum Anchor
    {
        TopLeft,
        TopCenter,
        TopRight,
        CenterLeft,
        Center,
        CenterRight,
        BottomLeft,
        BottomCenter,
        BottomRight
    }

    public class ImageStyle : INotifyPropertyChanged
    {
        private string filePath;
        private double scale = 1.0;
        private Anchor anchor = Anchor.TopLeft;
        private int offsetX;
        private int offsetY;
        private double opacity = 1.0;
        private int startMs;
        private int endMs;
        private bool loop;
        private int fadeIn;
        private int fadeOut;
       
        public ObservableCollection<Anchor> Anchors { get; } = new ObservableCollection<Anchor>(Enum.GetValues(typeof(Anchor)).Cast<Anchor>());


        public static readonly string[] ImageExtensions =
        {
            ".png", ".jpg", ".jpeg", ".bmp", ".webp",
            ".gif",
            ".mp4", ".mov", ".avi", ".mkv", ".webm"
        };

        public string FilePath
        {
            get => filePath;
            set { filePath = value; OnPropertyChanged(); }
        }

        public double Scale
        {
            get => scale;
            set { scale = value; OnPropertyChanged(); }
        }
       
        public Anchor Anchor
        {
            get => anchor;
            set { anchor = value; OnPropertyChanged(); }
        }

        public int OffsetX
        {
            get => offsetX;
            set { offsetX = value; OnPropertyChanged(); }
        }

        public int OffsetY
        {
            get => offsetY;
            set { offsetY = value; OnPropertyChanged(); }
        }

        public double Opacity
        {
            get => opacity;
            set { opacity = value; OnPropertyChanged(); }
        }

        public int StartMs
        {
            get => startMs;
            set { startMs = value; OnPropertyChanged(); }
        }

        public int EndMs
        {
            get => endMs;
            set { endMs = value; OnPropertyChanged(); }
        }

        public bool Loop
        {
            get => loop;
            set { loop = value; OnPropertyChanged(); }
        }


        public int FadeIn
        {
            get => fadeIn;
            set { fadeIn = value; OnPropertyChanged(); }
        }

        public int FadeOut
        {
            get => fadeOut;
            set { fadeOut = value; OnPropertyChanged(); }
        }

        // ---------- Command ----------
        public ICommand PickImageCommand => new RelayCommand(PickImage);

        private void PickImage()
        {
            using var dialog = new OpenFileDialog
            {
                Filter =
                    "Media files|*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif;*.mp4;*.mov;*.avi;*.mkv;*.webm"
            };

            if (dialog.ShowDialog() == DialogResult.OK)
                FilePath = dialog.FileName;
        }

        public event PropertyChangedEventHandler PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string name = null)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }

    public class ImageSection : EditableSection
    {
        public ImageSection()
        {
            SectionType = SectionType.Image;
        }
        public ImageStyle Style { get; } = new ImageStyle();
    }
    public class OverlayDto
    {
        public string file_path { get; set; }
        public double scale { get; set; }
        public string anchor { get; set; }
        public int offset_x { get; set; }
        public int offset_y { get; set; }
        public double opacity { get; set; }
        public int start_ms { get; set; }
        public int end_ms { get; set; }
        public bool loop { get; set; }
        public int fade_in { get; set; }
        public int fade_out { get; set; }
    }

}

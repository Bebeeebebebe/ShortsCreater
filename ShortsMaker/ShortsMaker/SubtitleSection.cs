using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Collections.ObjectModel;
using System.Linq;
using System.Windows.Input;
using System.Windows.Media;
using System.Drawing;
using System.Windows.Forms;

using MediaColor = System.Windows.Media.Color;
using DrawingColor = System.Drawing.Color;

namespace ShortsMaker
{
    public class SubtitleStyle : INotifyPropertyChanged
    {
        // ================== RelayCommand ==================
        public class RelayCommand : ICommand
        {
            private readonly Action execute;
            public RelayCommand(Action execute) => this.execute = execute;
            public bool CanExecute(object parameter) => true;
            public void Execute(object parameter) => execute();
            public event EventHandler CanExecuteChanged;
        }
        
        // ================== Fonts ==================
        public ObservableCollection<string> Fonts { get; } =
            new ObservableCollection<string>(
                System.Windows.Media.Fonts.SystemFontFamilies.Select(f => f.Source));

        // ================== Alignment ==================
        public ObservableCollection<int> Alignments { get; } =
            new ObservableCollection<int> { 1, 2, 3, 4, 5, 6, 7, 8, 9 };

        // ================== Commands (FIX) ==================
        public ICommand PickPrimaryColorCommand { get; }
        public ICommand PickOutlineColorCommand { get; }

        public SubtitleStyle()
        {
            PickPrimaryColorCommand =
                new RelayCommand(() => PickColor(c => PrimaryColor = c));

            PickOutlineColorCommand =
                new RelayCommand(() => PickColor(c => OutlineColor = c));
        }

        private void PickColor(Action<MediaColor> setter)
        {
            using var dialog = new ColorDialog();
            if (dialog.ShowDialog() == DialogResult.OK)
            {
                setter(MediaColor.FromRgb(
                    dialog.Color.R,
                    dialog.Color.G,
                    dialog.Color.B));
            }
        }

        // ================== Fields ==================
        private string font = "Arial";
        private int fontSize = 48;
        private MediaColor primaryColor = Colors.White;
        private MediaColor outlineColor = Colors.Black;
        private double outlineWidth = 3.0;
        private double shadowWidth = 0.0;
        private bool bold;
        private bool italic;
        private int alignment = 2;
        private int marginV = 60;
        private int marginL = 30;
        private int marginR = 30;
        private int fadeIn;
        private int fadeOut;

        // ================== Properties ==================
        public string Font { get => font; set { font = value; OnPropertyChanged(); } }
        public int FontSize { get => fontSize; set { fontSize = value; OnPropertyChanged(); } }

        public MediaColor PrimaryColor
        {
            get => primaryColor;
            set
            {
                if (primaryColor == value) return;
                primaryColor = value;

                OnPropertyChanged();
                OnPropertyChanged(nameof(PrimaryColorBrush));
                OnPropertyChanged(nameof(PrimaryColorAss));   // 🔥 FIX
            }
        }

        public MediaColor OutlineColor
        {
            get => outlineColor;
            set
            {
                if (outlineColor == value) return;
                outlineColor = value;

                OnPropertyChanged();
                OnPropertyChanged(nameof(OutlineColorBrush));
                OnPropertyChanged(nameof(OutlineColorAss));   // 🔥 FIX
            }
        }

        // ================== Brushes (FIX) ==================
        public SolidColorBrush PrimaryColorBrush
        {
            get
            {
                var b = new SolidColorBrush(PrimaryColor);
                b.Freeze(); // 🔥 FIX
                return b;
            }
        }

        public SolidColorBrush OutlineColorBrush
        {
            get
            {
                var b = new SolidColorBrush(OutlineColor);
                b.Freeze(); // 🔥 FIX
                return b;
            }
        }

        public double OutlineWidth { get => outlineWidth; set { outlineWidth = value; OnPropertyChanged(); } }
        public double ShadowWidth { get => shadowWidth; set { shadowWidth = value; OnPropertyChanged(); } }
        public bool Bold { get => bold; set { bold = value; OnPropertyChanged(); } }
        public bool Italic { get => italic; set { italic = value; OnPropertyChanged(); } }
        public int Alignment { get => alignment; set { alignment = value; OnPropertyChanged(); } }
        public int MarginV { get => marginV; set { marginV = value; OnPropertyChanged(); } }
        public int MarginL { get => marginL; set { marginL = value; OnPropertyChanged(); } }
        public int MarginR { get => marginR; set { marginR = value; OnPropertyChanged(); } }
        public int FadeIn { get => fadeIn; set { fadeIn = value; OnPropertyChanged(); } }
        public int FadeOut { get => fadeOut; set { fadeOut = value; OnPropertyChanged(); } }

        // ================== ASS ==================
        public string PrimaryColorAss =>
        $"&H00{PrimaryColor.B:X2}{PrimaryColor.G:X2}{PrimaryColor.R:X2}&";

        public string OutlineColorAss =>
            $"&H00{OutlineColor.B:X2}{OutlineColor.G:X2}{OutlineColor.R:X2}&";
        // ================== Notify ==================
        public event PropertyChangedEventHandler PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string name = null)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }

    public class SubtitleSection : EditableSection
    {
        public SubtitleSection()
        {
            SectionType = SectionType.Subtitle;
        }
        public SubtitleStyle Style { get; set; } = new SubtitleStyle();
    }
}
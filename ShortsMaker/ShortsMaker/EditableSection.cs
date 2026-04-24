using ShortsMaker;
using System.ComponentModel;

public abstract class EditableSection : INotifyPropertyChanged
{
    private string title;
    private bool isEditing;
    private bool isEnabled = true;

    public SectionType SectionType { get; protected set; }

    public string Title
    {
        get => title;
        set { title = value; OnPropertyChanged(nameof(Title)); }
    }

    public string Description { get; set; }

    public bool IsEditing
    {
        get => isEditing;
        set { isEditing = value; OnPropertyChanged(nameof(IsEditing)); }
    }

    public bool IsEnabled
    {
        get => isEnabled;
        set
        {
            if (isEnabled == value) return;
            isEnabled = value;
            OnPropertyChanged(nameof(IsEnabled));
        }
    }

    public event PropertyChangedEventHandler PropertyChanged;
    protected void OnPropertyChanged(string name) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
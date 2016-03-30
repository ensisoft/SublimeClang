

class GlobalClass
{
public:
    GlobalClass()
    {}

   ~GlobalClass()
    {}

    void public_function()
    {}

    void public_function_const() const
    {}

    void public_function_const() volatile
    {}

    template<typename T>
    void member_function_template()
    {}

protected:
    void protected_function()
    {}

private:
};


void global_function()
{}

namespace foobar {

} // foobar


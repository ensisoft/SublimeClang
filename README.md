SublimeClang Plugin for SublimeText2
====================================

Provides completions and code parsing through clang.

Original plugin by Fredrik Ehnbom.

Installation
------------------------------------

Support for Linux only.

NOTE: This plugin requires ctypes Python plugin! 
Unfortunately the python bundled with SublimeText2 does
not come with ctypes. By far the easiest way to work around
this is by using the python 2.6 provided by your system.

Then go into your SublimeClang2 installation folder
and make a symbolic link to your python. After this ST2
will use the system python instead of built-in python.

```
$ cd your/sublime-text-2/lib
$ ln -s /usr/lib/python2.6 python2.6
```


SublimeClang now requires that you've installed libclang in your system.
Currently supported version by the plugin is clang 3.7.1

Once you have all that crap out of the way then install the plugin by.

```
$ cd .config/sublime-text-2/Plugins
$ git clone https://github.com/ensisoft/SublimeClang
$ cd SublimeClang
$ make
```

Restart SublimeText. :metal:



Usage
-------------------------------------

After installation, suggestions from clang should be provided when triggering the autocomplete operation in Sublime Text 2. By default it'll inhibit the Sublime Text 2 built in word completion, but the inhibition can be disabled by setting the configuration option "inhibit_sublime_completions" to false.

If you modify a file that clang can compile and if there are any errors or warnings in that file, you should see the output in the output panel, as well as having the warnings and errors marked in the source file.

There's also the following key-bindings (tweak Default.sublime-keymaps to change):

      |alt+d,alt+d|Go to the parent reference of whatever is under the current cursor position|
      |alt+d,alt+i|Go to the implementation|
      |alt+d,alt+b|Go back to where you were before hitting alt+d,alt+d or alt+d,alt+i|
      |alt+d,alt+c|Clear the cache. Will force all files to be reparsed when needed|
      |alt+d,alt+w|Manually warm up the cache|
      |alt+d,alt+r|Manually reparse the current file|
      |alt+d,alt+t|Toggle whether Clang completion is enabled or not. Useful if the complete operation is slow and you only want to use it selectively|
      |alt+d,alt+p|Toggle the Clang output panel|
      |alt+d,alt+e|Go to next error or warning in the file|
      |alt+shift+d,alt+shift+e|Go to the previous error or warning in the file|
      |alt+d,alt+s|Run the Clang static analyzer on the current file|
      |alt+d,alt+o|Run the Clang static analyzer on the current project|
      |alt+d,alt+f|Toggle whether fast (but possibly inaccurate) completions are used or not|



License
--------------------------------------
This plugin is using the zlib license

{{{
Copyright (c) 2011-2012 Fredrik Ehnbom

This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

   1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required.

   2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.

   3. This notice may not be removed or altered from any source
   distribution.
}}}

---------------------------------------------------------

And in addition to this, clang itself is using the following license:

{{{
University of Illinois/NCSA
Open Source License

Copyright (c) 2003-2012 University of Illinois at Urbana-Champaign.
All rights reserved.

Developed by:

    LLVM Team

    University of Illinois at Urbana-Champaign

    http://llvm.org

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal with
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimers.

    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimers in the
      documentation and/or other materials provided with the distribution.

    * Neither the names of the LLVM Team, University of Illinois at
      Urbana-Champaign, nor the names of its contributors may be used to
      endorse or promote products derived from this Software without specific
      prior written permission.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
CONTRIBUTORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS WITH THE
SOFTWARE.
}}}

